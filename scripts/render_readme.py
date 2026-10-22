"""Render all result figures directly from retained raw command output."""

import json
from pathlib import Path


def read(name: str) -> dict:
    return json.loads(Path("docs/results", name).read_text())


bench = read("model-bench.json")
checks = read("checks.json")
media = read("demo-probe.json")
domain = read("domain-eval.json")
configs = bench["configurations"]
low = next(c for c in configs if c["max_new_tokens"] == 8)
high = next(c for c in configs if c["max_new_tokens"] == 32)
lo = next(r for r in low["loads"] if r["concurrency"] == 4)
hi = next(r for r in high["loads"] if r["concurrency"] == 4)
rows = "\n".join(
    f"| {c['max_new_tokens']} | {r['concurrency']} | {r['samples']} | {r['ttft_p50_ms']:.2f} / {r['ttft_p99_ms']:.2f} | {r['first_audio_p50_ms']:.2f} / {r['first_audio_p99_ms']:.2f} |"
    for c in configs
    for r in c["loads"]
)
voice = sorted(r["first_audio_ms"] for r in low["voice_rows"])
kill = low["real_backend_kill"]
assert kill["primary_exit"] < 0 and kill["surviving_turn"]["first_audio_ms"] > 0
assert low["barge_in"]["no_stale_frames_after_ack"]
text = f"""# Pulse

## Problem

Defend a voice turn's latency and cancellation boundary while real model workers stream, stall, fill their queues or crash.

**Status: partial.** [Public website and recorded demo](https://pulse-delta-ten-68.vercel.app) · [Repository](https://github.com/rjrddy/pulse) · [Quality checkpoint](docs/QUALITY.md). The Vercel site presents actual saved evidence; interactive model services are not hosted there.

## Results

| Proof | Measured result | Raw evidence |
|---|---|---|
| Local tests | {checks["go_race_tests_passed"]} Go race-enabled tests and {checks["python_tests_passed"]} Python tests passed | [required gate](docs/results/required-gates.log), [source hashes](docs/results/checks.json) |
| Configuration comparison at concurrency {lo["concurrency"]} | First-audio p99 {hi["first_audio_p99_ms"]:.2f} → {lo["first_audio_p99_ms"]:.2f} ms; {hi["max_new_tokens"] if "max_new_tokens" in hi else high["max_new_tokens"]} → {low["max_new_tokens"]} output-token cap; {lo["samples"]} samples per setting | [complete event traces](docs/results/model-bench.json) |
| Public-speech voice turns | {len(voice)} completed; first-audio range {voice[0]:.2f}–{voice[-1]:.2f} ms | voice_rows in [campaign](docs/results/model-bench.json) |
| Real worker kill and interruption | Primary exited with signal result {kill["primary_exit"]}; secondary completed the following turn; replacement after interruption completed with no stale frames after acknowledgement | real_backend_kill and barge_in in [campaign](docs/results/model-bench.json) |
| Actual browser recording | {float(media["format"]["duration"]):.2f} seconds | [video](docs/results/demo.webm), [ffprobe](docs/results/demo-probe.json), [browser events](docs/results/browser.json) |

Text → LLM → TTS through the Go WebSocket gateway:

| Output token cap | Concurrency | Samples | First token p50 / p99 ms | First audio p50 / p99 ms |
|---|---|---|---|---|
{rows}

The client clock starts immediately before sending a start frame on an established WebSocket. First token is the first nonempty decoded fragment; fragments are not necessarily tokenizer tokens. First audio means received PCM, before speaker playback. Text mode skips VAD/ASR. Small samples and interpolated quantiles are disclosed, not production capacity or an SLO. The shorter output cap changes answer length and inference/speech work; this is not an equal-quality optimization claim.

The real CPU models are faster-whisper tiny int8, SmolLM2 via Transformers, and Piper. [Environment and versions](docs/results/environment.json), [public model sources](docs/results/model-sources.json) and [saved dependency versions](requirements.lock) identify the setup. GPU and vLLM performance are **not measured**.

Caught failures are retained. The same [latency gate](scripts/budget_gate.py) rejects the longer-output setting against a configured budget and accepts the shorter one: [failing output](docs/results/budget-failure.json), [passing output](docs/results/budget-pass.json). [A real capacity-pressure failure](docs/results/caught-capacity-failure.log) exposed queue saturation being counted as poor backend health; a dedicated regression test now distinguishes those responses. CI also caught and retained a vulnerable base-image dependency, corrected before the passing checkpoint.

The domain experiment uses {domain["aggregates"][0]["samples"]} Piper-generated glossary phrases: term accuracy {domain["aggregates"][0]["term_accuracy"]:.2%} without hints / {domain["aggregates"][1]["term_accuracy"]:.2%} with a fixed glossary; WER {domain["aggregates"][0]["word_error_rate"]:.2%} / {domain["aggregates"][1]["word_error_rate"]:.2%}. [Raw audio, references and transcriptions](docs/results/domain-eval.json) are a tiny development check, not held-out human-speech accuracy. [The cold-start lab](docs/results/cold-start.json) measures fresh worker processes with a warm filesystem/model cache; container start and restore remain **not measured**.

![Pulse console](docs/results/ui-redesign/console-cover.png)

[Visual design references and UI checks](docs/UI.md) · [Redesigned console recording](docs/results/ui-redesign/demo.webm). Historical benchmark evidence remains separate.

## Architecture

```mermaid
flowchart LR
  U[React console / WebSocket client] --> G[Authenticated Go gateway]
  G --> C[Generation fence / deadline / bounded admission]
  C --> B[Epoch-fenced circuit breaker / pre-audio fallback]
  B --> W[Independent Python workers]
  W --> V[Energy VAD / faster-whisper]
  V --> L[SmolLM2 CPU / optional vLLM adapter]
  L --> T[Piper PCM chunks]
  T --> G
  G --> J[Flushed timing journal]
  G --> M[Metrics / stage events / trace IDs]
```

## Run it

```sh
python3 scripts/configure.py
docker compose up --build
```

Open http://localhost:8081 and sign in using the password in your ignored .env. The stack downloads actual open models and prepares public sample audio. No paid API key is required. See [development](docs/DEVELOPMENT.md) for native runs, actual benchmark commands, optional observability and the vLLM adapter. See [demo steps](docs/DEMO.md) and the [interview guide](INTERVIEW.md).

## Decisions and limits

- [Design](docs/DESIGN.md), [ADRs](docs/adr), [migration provenance](docs/migration/pulse.md) and [rehearsal drill](docs/DRILL.md) explain code and boundaries.
- The local path accepts complete utterances and returns token previews and sentence audio chunks. Continuous microphone capture, streaming ASR endpointing and phoneme-level streaming TTS are unfinished.
- Fallback only precedes visible audio. Mid-speech failure ends the turn; the process-kill experiment tests a following turn, not seamless continuation of audible speech.
- Cancellation fences future gateway frames and stops queued browser audio. Native inference can continue until its current operation returns; its worker slot remains occupied.
- Circuit state, login limits and admission are per gateway process. No tenant isolation, distributed quota, cross-region failover or replicated journal is implemented.
- History stores only timing/IDs/outcomes. Its single-process journal fsyncs before final acknowledgement; a partial line blocks startup for explicit recovery. Stateless hosting needs an external persistence adapter.
- Stage event tracing and trace IDs are implemented; an OTLP exporter and long-term tracing backend are not. Prometheus/Grafana compose services are optional; full provisioned dashboard automation is unfinished.
- The public site hosts recorded evidence. Interactive hosted inference, a measured vLLM/GPU deployment, container start/restore and broad domain evaluation remain open. All original repos and the existing portfolio remain intact.

## Next

Deploy provisioned model services and durable external history. Add capture/endpointing, incremental TTS, capacity-aware batching, equal-quality latency comparisons, measured GPU/vLLM serving, container checkpoint/restore, broad voice-domain evaluation and tenant-scoped limits. Stop for review before Gatekeeper.
"""
Path("README.md").write_text(text)
print("Rendered Pulse README from retained raw evidence.")
