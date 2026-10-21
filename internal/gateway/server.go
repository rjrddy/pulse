package gateway

import (
	"context"
	"crypto/hmac"
	"crypto/rand"
	"crypto/sha256"
	"crypto/subtle"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"github.com/gorilla/websocket"
	"log/slog"
	"net/http"
	"os"
	"strconv"
	"strings"
	"sync"
	"sync/atomic"
	"time"
)

type Server struct {
	Router                       *Router
	Journal                      *Journal
	Password, Token, Origin, Web string
	Secure                       bool
	active                       atomic.Int64
	turns                        atomic.Int64
	failures                     atomic.Int64
	fallbacks                    atomic.Int64
	mu                           sync.Mutex
	logins                       map[string]time.Time
}

func ID() string {
	b := make([]byte, 16)
	if _, e := rand.Read(b); e != nil {
		panic(e)
	}
	return hex.EncodeToString(b)
}
func (s *Server) signature(v string) string {
	m := hmac.New(sha256.New, []byte(s.Token))
	m.Write([]byte(v))
	return hex.EncodeToString(m.Sum(nil))
}
func (s *Server) authorized(r *http.Request) bool {
	if subtle.ConstantTimeCompare([]byte(r.Header.Get("Authorization")), []byte("Bearer "+s.Token)) == 1 {
		return true
	}
	c, e := r.Cookie("pulse_session")
	if e != nil {
		return false
	}
	parts := strings.Split(c.Value, ".")
	if len(parts) != 3 || !hmac.Equal([]byte(s.signature(parts[0]+"."+parts[1])), []byte(parts[2])) {
		return false
	}
	expiry, e := strconv.ParseInt(parts[1], 10, 64)
	return e == nil && time.Now().Unix() < expiry
}
func (s *Server) Handler() http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("GET /health", func(w http.ResponseWriter, r *http.Request) { writeJSON(w, map[string]string{"status": "ok"}) })
	mux.HandleFunc("POST /api/login", s.login)
	mux.HandleFunc("GET /api/history", s.guard(func(w http.ResponseWriter, r *http.Request) { writeJSON(w, s.Journal.History()) }))
	mux.HandleFunc("GET /api/status", s.guard(func(w http.ResponseWriter, r *http.Request) {
		back := map[string]string{}
		for _, b := range s.Router.Backends {
			back[b.Name] = b.Breaker.State()
		}
		writeJSON(w, map[string]any{"backends": back, "active": s.active.Load(), "turns": s.turns.Load(), "failures": s.failures.Load(), "fallbacks": s.fallbacks.Load(), "budget_ms": s.Router.Budget.Milliseconds()})
	}))
	mux.HandleFunc("GET /metrics", s.guard(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "text/plain; version=0.0.4")
		fmt.Fprintf(w, "pulse_active_sessions %d\npulse_turns_total %d\npulse_failures_total %d\npulse_fallbacks_total %d\n", s.active.Load(), s.turns.Load(), s.failures.Load(), s.fallbacks.Load())
	}))
	mux.HandleFunc("GET /api/stream", s.guard(s.socket))
	mux.Handle("GET /", http.FileServer(http.Dir(s.Web)))
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("X-Content-Type-Options", "nosniff")
		w.Header().Set("Referrer-Policy", "same-origin")
		w.Header().Set("Cache-Control", "no-store")
		mux.ServeHTTP(w, r)
	})
}
func writeJSON(w http.ResponseWriter, v any) {
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(v)
}
func (s *Server) guard(h http.HandlerFunc) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if !s.authorized(r) {
			http.Error(w, "authentication required", 401)
			return
		}
		h(w, r)
	}
}
func (s *Server) login(w http.ResponseWriter, r *http.Request) {
	if r.Header.Get("Origin") != "" && r.Header.Get("Origin") != s.Origin {
		http.Error(w, "origin rejected", 403)
		return
	}
	s.mu.Lock()
	if s.logins == nil {
		s.logins = map[string]time.Time{}
	}
	now := time.Now()
	for k, t := range s.logins {
		if now.Sub(t) > time.Minute {
			delete(s.logins, k)
		}
	}
	if t, ok := s.logins["global"]; ok && now.Sub(t) < time.Second {
		s.mu.Unlock()
		http.Error(w, "rate limited", 429)
		return
	}
	s.logins["global"] = now
	s.mu.Unlock()
	r.Body = http.MaxBytesReader(w, r.Body, 4096)
	var input struct {
		Password string `json:"password"`
	}
	if json.NewDecoder(r.Body).Decode(&input) != nil || subtle.ConstantTimeCompare([]byte(input.Password), []byte(s.Password)) != 1 {
		http.Error(w, "invalid credentials", 401)
		return
	}
	v := ID() + "." + strconv.FormatInt(now.Add(8*time.Hour).Unix(), 10)
	value := v + "." + s.signature(v)
	http.SetCookie(w, &http.Cookie{Name: "pulse_session", Value: value, Path: "/", HttpOnly: true, Secure: s.Secure, SameSite: http.SameSiteStrictMode, MaxAge: 28800})
	writeJSON(w, map[string]bool{"ok": true})
}

type message struct {
	Type       string `json:"type"`
	Audio      string `json:"audio"`
	SampleRate int    `json:"sample_rate"`
	Mode       string `json:"mode"`
	Text       string `json:"text"`
}

func (s *Server) socket(w http.ResponseWriter, r *http.Request) {
	if s.active.Add(1) > 32 {
		s.active.Add(-1)
		http.Error(w, "session capacity", 429)
		return
	}
	defer s.active.Add(-1)
	up := websocket.Upgrader{CheckOrigin: func(r *http.Request) bool { return r.Header.Get("Origin") == "" || r.Header.Get("Origin") == s.Origin }}
	conn, e := up.Upgrade(w, r, nil)
	if e != nil {
		return
	}
	defer conn.Close()
	conn.SetReadLimit(4 << 20)
	conn.SetReadDeadline(time.Now().Add(5 * time.Minute))
	var mu sync.Mutex
	var generation uint64
	var cancel context.CancelFunc
	var tasks sync.WaitGroup
	defer func() {
		if cancel != nil {
			cancel()
		}
		tasks.Wait()
	}()
	send := func(gen uint64, event Event) error {
		mu.Lock()
		defer mu.Unlock()
		if gen != generation {
			return context.Canceled
		}
		event.Generation = gen
		conn.SetWriteDeadline(time.Now().Add(3 * time.Second))
		return conn.WriteJSON(event)
	}
	for {
		var m message
		if e = conn.ReadJSON(&m); e != nil {
			return
		}
		if m.Type != "start" && m.Type != "interrupt" {
			continue
		}
		mu.Lock()
		generation++
		gen := generation
		mu.Unlock()
		if cancel != nil {
			cancel()
		}
		if m.Type == "interrupt" {
			send(gen, Event{Type: "cancelled"})
			continue
		}
		raw, err := base64.StdEncoding.DecodeString(m.Audio)
		if err != nil || len(raw) > 16000*2*20 || len(raw)%2 != 0 || (m.SampleRate != 16000) || len(m.Text) > 800 || (m.Mode != "" && m.Mode != "text") {
			send(gen, Event{Type: "error", Error: "invalid input"})
			continue
		}
		if m.Mode == "text" && len(strings.TrimSpace(m.Text)) == 0 {
			send(gen, Event{Type: "error", Error: "text required"})
			continue
		}
		ctx, stop := context.WithCancel(r.Context())
		cancel = stop
		s.turns.Add(1)
		tasks.Add(1)
		go func(gen uint64, input Input) {
			defer tasks.Done()
			started := time.Now()
			first := float64(0)
			backend := ""
			id := ID()
			outcome := "done"
			err := s.Router.Route(ctx, input, func(event Event) error {
				if event.Type == "audio" && first == 0 {
					first = float64(time.Since(started).Microseconds()) / 1000
				}
				event.TraceID = id
				backend = event.Backend
				if event.Type == "attempt_reset" {
					s.fallbacks.Add(1)
				}
				if event.Type == "done" {
					return nil
				}
				return send(gen, event)
			})
			if err != nil {
				outcome = "failed"
				if errors.Is(err, context.Canceled) {
					outcome = "cancelled"
				} else {
					s.failures.Add(1)
				}
			}
			record := Record{ID: id, Outcome: outcome, Backend: backend, FirstAudioMS: first, TotalMS: float64(time.Since(started).Microseconds()) / 1000, At: time.Now().UTC()}
			if e := s.Journal.Append(record); e != nil {
				send(gen, Event{Type: "error", Error: "history persistence failed"})
				return
			}
			slog.Info("turn_finished", "turn", id, "trace_id", id, "outcome", outcome, "backend", backend, "first_audio_ms", first, "total_ms", record.TotalMS)
			if err != nil {
				send(gen, Event{Type: "error", Error: outcome})
			} else {
				send(gen, Event{Type: "done", ElapsedMS: record.TotalMS, Text: id})
			}
		}(gen, Input{Audio: m.Audio, SampleRate: m.SampleRate, Mode: m.Mode, Text: m.Text})
	}
}
func NewFromEnv() (*Server, error) {
	password, token := os.Getenv("PULSE_PASSWORD"), os.Getenv("PULSE_TOKEN")
	if len(password) < 16 || len(token) < 24 {
		return nil, errors.New("PULSE_PASSWORD and PULSE_TOKEN must be provisioned")
	}
	var backends []*Backend
	for i, url := range strings.Split(os.Getenv("PULSE_BACKENDS"), ",") {
		if !strings.HasPrefix(url, "http://") && !strings.HasPrefix(url, "https://") {
			return nil, errors.New("invalid backend URL")
		}
		backends = append(backends, &Backend{Name: fmt.Sprintf("worker-%d", i+1), URL: strings.TrimRight(url, "/"), Breaker: &Breaker{Threshold: 2, Cooldown: 3 * time.Second}})
	}
	budget := 40 * time.Second
	if v := os.Getenv("PULSE_BUDGET_MS"); v != "" {
		n, e := strconv.Atoi(v)
		if e != nil || n < 100 || n > 120000 {
			return nil, errors.New("invalid budget")
		}
		budget = time.Duration(n) * time.Millisecond
	}
	dir := os.Getenv("PULSE_DATA")
	if dir == "" {
		dir = "data"
	}
	if e := os.MkdirAll(dir, 0700); e != nil {
		return nil, e
	}
	j, e := OpenJournal(dir + "/turns.jsonl")
	if e != nil {
		return nil, e
	}
	web := os.Getenv("PULSE_WEB")
	if web == "" {
		web = "apps/web/dist"
	}
	origin := os.Getenv("PULSE_ORIGIN")
	if origin == "" {
		origin = "http://localhost:8081"
	}
	return &Server{Router: &Router{Backends: backends, Client: &http.Client{}, Budget: budget, AttemptBudget: budget / 2, Slots: make(chan struct{}, 8), WorkerToken: token}, Journal: j, Password: password, Token: token, Origin: origin, Web: web, Secure: os.Getenv("COOKIE_SECURE") == "1"}, nil
}
