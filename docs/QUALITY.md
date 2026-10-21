# Pulse quality checkpoint

**Partial.** The local CPU implementation, real-model benchmark campaign, browser verification, recording, and public evidence website are implemented. Interactive hosted services, a measured vLLM/GPU run, continuous audio capture/streaming endpointing, broad domain evaluation, and container start/restore measurements remain open.

| Check | Status | Evidence |
|---|---|---|
| Hard concurrency core explained | PASS | DESIGN.md, gateway generation/breaker epochs, race tests |
| API, auth, persistence, actual React UI | PASS locally | browser.json, journal reopen/concurrency tests, screen recording |
| Fresh-clone one-command containers | PASS on recorded source | linux-compose/compose-smoke.json; independent native clone also passes |
| Integration/property/chaos checks | PASS locally | required-gates.log, model-bench.json, worker tests |
| Measured numbers saved | PASS | client event traces, voice rows, cold-start.json, domain-eval.json |
| Caught failure | PASS | budget-failure.json; capacity-failure log and regression test; initial CI failure retained |
| ADRs and interview/rehearsal kit | PASS | adr/, INTERVIEW.md, DRILL.md |
| Dependency scans | PASS in saved local runs | security.log and python-audit.json; initial vulnerable graph retained |
| Real screen recording | PASS | demo.webm, demo-probe.json |
| Public Vercel website | Recorded evidence only | deployment proof records exact URL; not a hosted inference claim |
| Final CI green | PASS on recorded source; verify final push in workspace PULSE_VERIFICATION.json | CI also scans the actual worker container |
| vLLM/GPU serving | NOT MEASURED | optional compatible endpoint adapter only |
| Container start/restore lab | NOT MEASURED | cold-start.json measures fresh processes with warm filesystem cache |

Measurement limits: the model sweep uses small explicitly counted local samples. Text input skips VAD/ASR. First token is a nonempty decoded fragment, not necessarily one tokenizer token. First audio is PCM received after an already established WebSocket, not capture-to-ear latency. Smaller token caps change output length and work, not equal-quality inference speed. Domain speech is generated from a fixed glossary and is not held out. The worker-kill proof checks a subsequent pre-audio turn, not seamless continuation of audible speech.

The journal is single-writer and fsyncs before final acknowledgement. It is not replicated; partial final lines require explicit recovery. Speech and prompts are transient. Worker cancellation is cooperative across native operations, so stale inference may use CPU until it returns. Hosted stateless deployment needs external durable history and provisioned worker services. All old repositories and the existing portfolio remain unchanged. Stop before Gatekeeper.

Public evidence website: https://pulse-delta-ten-68.vercel.app. Its recorded scope, selector and responsive checks are saved in docs/results/vercel.json.
