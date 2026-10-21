package main

import (
	"context"
	"github.com/rjrddy/pulse/internal/gateway"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"
)

func main() {
	slog.SetDefault(slog.New(slog.NewJSONHandler(os.Stdout, nil)))
	app, e := gateway.NewFromEnv()
	if e != nil {
		slog.Error("configuration_failed", "error", e)
		os.Exit(1)
	}
	defer app.Journal.Close()
	port := os.Getenv("PORT")
	if port == "" {
		port = "8081"
	}
	server := &http.Server{Addr: ":" + port, Handler: app.Handler(), ReadHeaderTimeout: 5 * time.Second, IdleTimeout: 30 * time.Second, MaxHeaderBytes: 16384}
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()
	go func() {
		<-ctx.Done()
		c, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()
		server.Shutdown(c)
	}()
	slog.Info("listening", "port", port)
	if e = server.ListenAndServe(); e != nil && e != http.ErrServerClosed {
		slog.Error("server_failed")
		os.Exit(1)
	}
}
