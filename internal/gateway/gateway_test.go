package gateway

import (
	"context"
	"encoding/json"
	"errors"
	"github.com/gorilla/websocket"
	"io"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
	"time"
)

func fixture(handler http.HandlerFunc) *httptest.Server { return httptest.NewServer(handler) }
func backend(name, url string) *Backend {
	return &Backend{Name: name, URL: url, Breaker: &Breaker{Threshold: 1, Cooldown: time.Second}}
}
func router(bs ...*Backend) *Router {
	return &Router{Backends: bs, Client: &http.Client{}, Budget: time.Second, AttemptBudget: 100 * time.Millisecond, Slots: make(chan struct{}, 2), WorkerToken: "synthetic-test-token-only-123456"}
}
func emit(w http.ResponseWriter, e Event) {
	json.NewEncoder(w).Encode(e)
	if f, ok := w.(http.Flusher); ok {
		f.Flush()
	}
}
func TestBreakerSingleHalfOpenProbe(t *testing.T) {
	b := backend("", "").Breaker
	b.Finish(0, time.Now().Add(-2*time.Second), true, false)
	var accepted atomic.Int64
	var wg sync.WaitGroup
	for range 100 {
		wg.Add(1)
		go func() {
			defer wg.Done()
			if _, ok := b.Acquire(time.Now()); ok {
				accepted.Add(1)
			}
		}()
	}
	wg.Wait()
	if accepted.Load() != 1 {
		t.Fatal(accepted.Load())
	}
	b.Finish(1, time.Now(), false, false)
	_, ok := b.Acquire(time.Now())
	if !ok || b.State() != "closed" {
		t.Fatal("did not close")
	}
}
func TestCancelledAttemptDoesNotTripBreaker(t *testing.T) {
	b := backend("", "").Breaker
	b.Finish(0, time.Now(), true, true)
	if b.State() != "closed" {
		t.Fatal("client cancellation opened breaker")
	}
}
func TestFallbackResetsBeforeAudio(t *testing.T) {
	a := fixture(func(w http.ResponseWriter, r *http.Request) { emit(w, Event{Type: "token", Text: "discard preview"}) })
	defer a.Close()
	b := fixture(func(w http.ResponseWriter, r *http.Request) {
		emit(w, Event{Type: "audio", Audio: "AA=="})
		emit(w, Event{Type: "done"})
	})
	defer b.Close()
	var events []string
	e := router(backend("a", a.URL), backend("b", b.URL)).Route(context.Background(), Input{}, func(e Event) error { events = append(events, e.Type); return nil })
	if e != nil || strings.Join(events, ",") != "token,attempt_reset,audio,done" {
		t.Fatal(e, events)
	}
}
func TestNoReplayAfterVisibleAudio(t *testing.T) {
	a := fixture(func(w http.ResponseWriter, r *http.Request) { emit(w, Event{Type: "audio", Audio: "AA=="}) })
	defer a.Close()
	var calls atomic.Int64
	b := fixture(func(w http.ResponseWriter, r *http.Request) { calls.Add(1) })
	defer b.Close()
	e := router(backend("a", a.URL), backend("b", b.URL)).Route(context.Background(), Input{}, func(Event) error { return nil })
	if e == nil || calls.Load() != 0 {
		t.Fatal("repeated visible speech", e, calls.Load())
	}
}
func TestDeadlineCancelsBackend(t *testing.T) {
	finished := make(chan struct{})
	a := fixture(func(w http.ResponseWriter, r *http.Request) {
		io.Copy(io.Discard, r.Body)
		<-r.Context().Done()
		close(finished)
	})
	defer a.Close()
	r := router(backend("a", a.URL))
	r.Budget = 35 * time.Millisecond
	r.AttemptBudget = time.Second
	started := time.Now()
	e := r.Route(context.Background(), Input{}, func(Event) error { return nil })
	if !errors.Is(e, context.DeadlineExceeded) || time.Since(started) > 300*time.Millisecond {
		t.Fatal(e)
	}
	select {
	case <-finished:
	case <-time.After(time.Second):
		t.Fatal("HTTP not cancelled")
	}
}
func TestAdmissionBounded(t *testing.T) {
	r := router()
	r.Slots <- struct{}{}
	r.Slots <- struct{}{}
	if !errors.Is(r.Route(context.Background(), Input{}, func(Event) error { return nil }), ErrBusy) {
		t.Fatal("capacity not enforced")
	}
}
func TestJournalReopenAndCorruption(t *testing.T) {
	p := filepath.Join(t.TempDir(), "history")
	j, e := OpenJournal(p)
	if e != nil {
		t.Fatal(e)
	}
	if e = j.Append(Record{ID: "test", Outcome: "done"}); e != nil {
		t.Fatal(e)
	}
	j.Close()
	j, e = OpenJournal(p)
	if e != nil || len(j.History()) != 1 {
		t.Fatal(e)
	}
	j.Close()
	os.WriteFile(p, []byte("{truncated"), 0600)
	if j, e = OpenJournal(p); e == nil {
		j.Close()
		t.Fatal("silently accepted corrupt history")
	}
}
func TestConcurrentJournalWrites(t *testing.T) {
	j, e := OpenJournal(filepath.Join(t.TempDir(), "history"))
	if e != nil {
		t.Fatal(e)
	}
	defer j.Close()
	var wg sync.WaitGroup
	for range 40 {
		wg.Add(1)
		go func() {
			defer wg.Done()
			if e := j.Append(Record{ID: ID()}); e != nil {
				t.Error(e)
			}
		}()
	}
	wg.Wait()
	if len(j.History()) != 40 {
		t.Fatal("lost records")
	}
}
func TestClientSendFailureIsNotSuccess(t *testing.T) {
	a := fixture(func(w http.ResponseWriter, r *http.Request) { emit(w, Event{Type: "token"}) })
	defer a.Close()
	sentinel := errors.New("client write failed")
	if e := router(backend("a", a.URL)).Route(context.Background(), Input{}, func(Event) error { return sentinel }); !errors.Is(e, sentinel) {
		t.Fatal(e)
	}
}
func TestWebsocketGenerationFencesInterruptedTurn(t *testing.T) {
	a := fixture(func(w http.ResponseWriter, r *http.Request) {
		emit(w, Event{Type: "token", Text: "started"})
		select {
		case <-r.Context().Done():
		case <-time.After(20 * time.Millisecond):
			emit(w, Event{Type: "audio", Audio: "AA=="})
			emit(w, Event{Type: "done"})
		}
	})
	defer a.Close()
	j, _ := OpenJournal(filepath.Join(t.TempDir(), "history"))
	defer j.Close()
	s := &Server{Router: router(backend("a", a.URL)), Journal: j, Token: "synthetic-test-token-only-123456", Web: t.TempDir(), Origin: "https://allowed.test"}
	httpServer := httptest.NewServer(s.Handler())
	defer httpServer.Close()
	headers := http.Header{"Authorization": []string{"Bearer " + s.Token}, "Origin": []string{s.Origin}}
	c, _, e := websocket.DefaultDialer.Dial("ws"+strings.TrimPrefix(httpServer.URL, "http")+"/api/stream", headers)
	if e != nil {
		t.Fatal(e)
	}
	defer c.Close()
	c.SetReadDeadline(time.Now().Add(2 * time.Second))
	c.WriteJSON(message{Type: "start", Mode: "text", Text: "test", SampleRate: 16000})
	var event Event
	c.ReadJSON(&event)
	if event.Type != "token" {
		t.Fatal(event)
	}
	c.WriteJSON(message{Type: "interrupt"})
	c.ReadJSON(&event)
	if event.Type != "cancelled" || event.Generation != 2 {
		t.Fatal(event)
	}
	c.WriteJSON(message{Type: "start", Mode: "text", Text: "new turn", SampleRate: 16000})
	for {
		if e = c.ReadJSON(&event); e != nil {
			t.Fatal(e)
		}
		if event.Generation != 3 {
			t.Fatal("stale frame after cancellation", event)
		}
		if event.Type == "done" {
			break
		}
	}
}
func TestAuthAndOriginRejected(t *testing.T) {
	j, _ := OpenJournal(filepath.Join(t.TempDir(), "h"))
	defer j.Close()
	s := &Server{Journal: j, Router: router(), Token: "synthetic-test-token-only-123456", Origin: "https://good.test", Web: t.TempDir()}
	srv := httptest.NewServer(s.Handler())
	defer srv.Close()
	r, _ := http.Get(srv.URL + "/api/history")
	r.Body.Close()
	if r.StatusCode != 401 {
		t.Fatal(r.StatusCode)
	}
	h := http.Header{"Authorization": []string{"Bearer " + s.Token}, "Origin": []string{"https://bad.test"}}
	c, response, e := websocket.DefaultDialer.Dial("ws"+strings.TrimPrefix(srv.URL, "http")+"/api/stream", h)
	if c != nil {
		c.Close()
	}
	if e == nil || response.StatusCode != 403 {
		t.Fatal("cross-origin accepted")
	}
}

func TestStaleBreakerCompletionCannotReleaseProbe(t *testing.T) {
	b := backend("", "").Breaker
	old, _ := b.Acquire(time.Now())
	b.Finish(old, time.Now().Add(-2*time.Second), true, false)
	probe, ok := b.Acquire(time.Now())
	if !ok {
		t.Fatal("probe not admitted")
	}
	b.Finish(old, time.Now(), false, false)
	if _, ok = b.Acquire(time.Now()); ok {
		t.Fatal("old completion released current probe")
	}
	b.Finish(probe, time.Now(), false, false)
	if b.State() != "closed" {
		t.Fatal("probe did not close")
	}
}
