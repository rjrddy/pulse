# Pulse interview guide

## Pitch

Pulse is a voice inference system whose hard part is ownership under deadlines and interruption. A Go gateway accepts authenticated WebSocket turns, routes them to real Python model workers, and tracks when text and audio become visible. It can retry a failed backend before audio is emitted, but it refuses to repeat speech after that boundary. Session generations fence an interrupted turn, and circuit-breaker epochs fence stale health results.

The measured path uses actual open CPU models. The README links the complete client event traces, concurrency sweep, backend process-kill run and caught latency-gate failure. GPU serving, vLLM performance and container restore are separate unfinished work. This is a measured systems project, not a claim of production voice quality.

## Architecture walkthrough

Start in `internal/gateway/server.go`: inspect bearer/session authentication, the WebSocket origin check, bounded input, generation increment and writer mutex. Follow the turn into `router.go`: total deadline, shorter attempt deadline, admission slots, breaker ticket, bounded worker stream and visibility boundary. Check the attempt-reset event and why audio prohibits retry.

Open `worker/app.py`. The energy VAD trims quiet edges without deleting interior pauses. ASR uses real faster-whisper. The LLM yields actual text fragments, then Piper yields PCM chunks with explicit rates. The producer owns its semaphore slot even when HTTP disconnects. Review the bounded queue and cooperative cancellation across native operations.

Return to the gateway journal: summaries exclude prompt, transcript and audio; fsync precedes final acknowledgement. The React console independently stops scheduled audio on barge-in, displays actual stage timings, and reloads persisted history. End with the race tests and raw benchmark boundary; discuss every partial item in QUALITY.md.

## Chosen tradeoffs

- Single-process journal versus external Postgres: simpler local durability, explicit single-writer and hosted-persistence limits.
- Fallback before visible audio versus replay: successful recovery for pre-audio failure, visible failure after partial speech.
- CPU small models versus an unapproved GPU rental: reproducible genuine model work with limited answer quality and separate vLLM evidence gaps.
- Sentence-chunk TTS versus phoneme streaming: simpler PCM framing at a higher first-audio latency.
- Serial model executor versus concurrent inference: bounded native memory/work with visible queueing under load.

## Failure handling

- Primary process exits: retry the secondary before audio, with a reset for token previews.
- User interrupts: advance generation, cancel worker HTTP, stop client audio sources, reject all old-generation frames.
- Backend stalls: attempt and total deadlines cancel the transport; a partial-audio failure is never replayed.
- Overload: bounded session/turn/worker slots return visible failure; no unlimited inference queue.
- Journal corruption or disk failure: reject startup or terminal acknowledgement; do not pretend history was saved.

## Likely questions

1. **Where is the concurrency invariant?** Generation validation and socket write share a mutex; breaker completions carry epochs.
2. **What does durability mean?** A completed turn's summary was flushed, assuming the host/filesystem honors fsync. No replicated-storage claim.
3. **Is there exactly-once execution?** No. Pre-audio attempts may run on multiple workers; visible output has a stricter replay boundary.
4. **What is the retry budget?** The total context bounds all attempts, and each worker has a shorter deadline. Configured defaults are inspectable in code and status.
5. **Why can cancellation leave CPU work running?** Native inference is not forcibly preempted; the worker owns its slot until return.
6. **Why use epochs in a breaker?** A request from before opening must not reset the new half-open probe.
7. **How are tokens measured?** First nonempty text fragment received at the client. Fragments need not equal tokenizer tokens.
8. **How is first audio measured?** At received PCM frame, before browser scheduling and hardware playback. Do not claim capture-to-ear latency.
9. **What improves p99?** The saved token-cap experiment changes work/output length. It is not an equal-quality model optimization.
10. **Does the kill test prove continuous audio survives?** It proves a subsequent pre-audio turn falls back; it does not prove seamless mid-utterance continuation.
11. **How does auth work?** A provisioned high-entropy operator password signs bounded-lifetime HttpOnly SameSite sessions; worker calls use a distinct provisioned bearer value.
12. **What does the VAD guarantee?** Energy trimming and input bounds, not semantic speech detection or noisy-environment robustness.
13. **Why is vLLM partial?** A compatible adapter and configuration are not a measured model service. The local host has no CUDA GPU.
14. **How would you scale?** External durable history, scoped tenants, per-worker capacity-aware routing, batching and measured GPU pools.
15. **What is not measured?** GPU/vLLM throughput, container restore, capture/device playback latency, multi-region failures and production language/voice quality.

## With more time

Add continuous capture/streaming endpointing, phoneme-level TTS streaming, capacity-aware batching, external transactional history, a real vLLM serving run, container checkpoint/restore experiments, broad public voice/domain evaluation, tenant isolation and equal-answer-quality latency comparisons.
