# Pulse design

The difficult boundary is cancellation while a slow inference backend is streaming, especially when a new voice turn interrupts an old one. A successful HTTP status is insufficient proof that audio reached the client before its deadline.

The Go gateway owns session generations. Every accepted turn receives a monotonically increasing generation. Cancellation increments that generation under the same mutex used to send frames: an old generation cannot send a frame after the cancellation acknowledgement. Request cancellation reaches the Python worker over HTTP. Model inference may finish an already running native operation; worker admission remains bounded while that operation runs.

A deadline covers queue admission through the first and last emitted audio frames. Each backend attempt has a shorter deadline. The circuit breaker counts transport/server failures, opens after a threshold, and admits one half-open probe. Client cancellation does not count as a backend failure. Fallback is permitted only before audio becomes visible; an explicit attempt-reset event invalidates earlier transcript/token previews. Once audio is visible, retry could repeat speech, so failure ends that turn instead.

Workers process bounded PCM input through energy-based VAD, faster-whisper ASR, a real small causal language model, and Piper TTS. The CPU development path uses Transformers; optional vLLM uses its OpenAI-compatible completion stream. The two paths have separate measurement labels; a CPU result is never labeled vLLM or GPU throughput. PCM is mono signed 16-bit, with explicit sample rates. No personal audio is retained.

The append-only gateway journal stores turn IDs, timing summaries, backend identity, and outcomes, not audio or transcripts. A write is flushed before its final event is acknowledged. This is single-process durable history with a Docker volume, not a replicated database. The console shows actual worker events and completed history. Prometheus counters and per-stage traces expose deadline/fallback behavior.

Only public sample speech and generated synthetic phrases are used for saved evidence. Microphone capture requires an explicit user action and is transient. Development evidence must distinguish real model results from deterministic protocol fixtures. Container restore and vLLM/GPU measurements remain partial unless actually run.
