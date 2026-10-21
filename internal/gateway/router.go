package gateway

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"strings"
	"sync"
	"time"
)

// Breaker permits exactly one probe after the cooldown. Cancellation releases it.
type Breaker struct {
	mu        sync.Mutex
	failures  int
	opened    time.Time
	probe     bool
	Threshold int
	Cooldown  time.Duration
}

func (b *Breaker) Acquire(now time.Time) bool {
	b.mu.Lock()
	defer b.mu.Unlock()
	if b.opened.IsZero() {
		return true
	}
	if now.Sub(b.opened) < b.Cooldown || b.probe {
		return false
	}
	b.probe = true
	return true
}
func (b *Breaker) Finish(now time.Time, failed, cancelled bool) {
	b.mu.Lock()
	defer b.mu.Unlock()
	wasProbe := b.probe
	b.probe = false
	if cancelled {
		return
	}
	if !failed {
		b.failures = 0
		b.opened = time.Time{}
		return
	}
	b.failures++
	if wasProbe || b.failures >= b.Threshold {
		b.opened = now
	}
}
func (b *Breaker) State() string {
	b.mu.Lock()
	defer b.mu.Unlock()
	if !b.opened.IsZero() {
		return "open"
	}
	return "closed"
}

type Event struct {
	TraceID    string  `json:"trace_id,omitempty"`
	Type       string  `json:"type"`
	Stage      string  `json:"stage,omitempty"`
	Text       string  `json:"text,omitempty"`
	Audio      string  `json:"audio,omitempty"`
	SampleRate int     `json:"sample_rate,omitempty"`
	Generation uint64  `json:"generation"`
	Attempt    int     `json:"attempt,omitempty"`
	Backend    string  `json:"backend,omitempty"`
	ElapsedMS  float64 `json:"elapsed_ms"`
	DurationMS float64 `json:"duration_ms,omitempty"`
	Error      string  `json:"error,omitempty"`
}
type Input struct {
	Audio      string `json:"audio"`
	SampleRate int    `json:"sample_rate"`
	Mode       string `json:"mode,omitempty"`
	Text       string `json:"text,omitempty"`
}
type Backend struct {
	Name, URL string
	Breaker   *Breaker
}
type Router struct {
	Backends              []*Backend
	Client                *http.Client
	Budget, AttemptBudget time.Duration
	Slots                 chan struct{}
	WorkerToken           string
}

var ErrBusy = errors.New("admission capacity reached")
var ErrBackend = errors.New("all backends failed before audio")

// Route retries only before visible audio; resets token previews between attempts.
func (r *Router) Route(ctx context.Context, input Input, send func(Event) error) error {
	select {
	case r.Slots <- struct{}{}:
		defer func() { <-r.Slots }()
	default:
		return ErrBusy
	}
	ctx, cancel := context.WithTimeout(ctx, r.Budget)
	defer cancel()
	raw, err := json.Marshal(input)
	if err != nil {
		return err
	}
	started := time.Now()
	for i, b := range r.Backends {
		if ctx.Err() != nil {
			return ctx.Err()
		}
		if !b.Breaker.Acquire(time.Now()) {
			continue
		}
		ac, stop := context.WithTimeout(ctx, r.AttemptBudget)
		req, err := http.NewRequestWithContext(ac, "POST", b.URL+"/stream", strings.NewReader(string(raw)))
		if err != nil {
			stop()
			b.Breaker.Finish(time.Now(), true, false)
			return err
		}
		req.Header.Set("Content-Type", "application/json")
		req.Header.Set("Authorization", "Bearer "+r.WorkerToken)
		response, err := r.Client.Do(req)
		visible := false
		done := false
		sendFailed := false
		if err == nil {
			if response.StatusCode != http.StatusOK {
				err = errors.New("worker unavailable")
			} else {
				dec := json.NewDecoder(io.LimitReader(response.Body, 16<<20))
				for {
					var event Event
					err = dec.Decode(&event)
					if err != nil {
						break
					}
					if event.Type != "stage" && event.Type != "token" && event.Type != "audio" && event.Type != "transcript" && event.Type != "done" && event.Type != "error" {
						err = errors.New("invalid worker event")
						break
					}
					event.Attempt = i + 1
					event.Backend = b.Name
					event.ElapsedMS = float64(time.Since(started).Microseconds()) / 1000
					if event.Type == "error" {
						err = errors.New("worker inference failed")
						break
					}
					if event.Type == "audio" {
						visible = true
					}
					if err = send(event); err != nil {
						sendFailed = true
						break
					}
					if event.Type == "done" {
						done = true
						break
					}
				}
			}
			response.Body.Close()
		}
		cancelled := ctx.Err() != nil || sendFailed
		b.Breaker.Finish(time.Now(), !done, cancelled)
		stop()
		if done {
			return nil
		}
		if cancelled {
			if ctx.Err() != nil {
				return ctx.Err()
			}
			return err
		}
		if visible {
			return errors.New("backend failed after audio; replay prohibited")
		}
		if err = send(Event{Type: "attempt_reset", Backend: b.Name, Attempt: i + 1, ElapsedMS: float64(time.Since(started).Microseconds()) / 1000}); err != nil {
			return err
		}
	}
	if ctx.Err() != nil {
		return ctx.Err()
	}
	return ErrBackend
}
