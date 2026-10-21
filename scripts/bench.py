"""Real independent-process CPU voice/load/kill campaign; no simulated model timings."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any

from websockets.asyncio.client import connect

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/results"
TOKEN = "synthetic-benchmark-token-only-123456789"
ENV = {
    **os.environ,
    "PULSE_TOKEN": TOKEN,
    "PULSE_PASSWORD": "synthetic-benchmark-password",
    "PULSE_ORIGIN": "http://localhost:18081",
    "PULSE_DATA": str(ROOT / ".cache/bench-history"),
    "PULSE_BACKENDS": "http://127.0.0.1:18091,http://127.0.0.1:18092",
    "PORT": "18081",
    "TOKENIZERS_PARALLELISM": "false",
    "OMP_NUM_THREADS": "2",
}


def quantile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    position = q * (len(ordered) - 1)
    low = int(position)
    return ordered[low] + (ordered[min(low + 1, len(ordered) - 1)] - ordered[low]) * (
        position - low
    )


def wait_health(port: int) -> float:
    started = time.perf_counter()
    for _ in range(300):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=1) as response:
                if response.status == 200:
                    return (time.perf_counter() - started) * 1000
        except OSError:
            time.sleep(0.1)
    raise RuntimeError("process did not become ready")


async def turn(mode: str = "text", interrupt: bool = False) -> dict[str, Any]:
    events: list[dict[str, Any]] = []
    pcm = (ROOT / "apps/web/dist/sample/sample.pcm").read_bytes() if mode == "audio" else b""
    async with connect(
        "ws://127.0.0.1:18081/api/stream",
        additional_headers={"Authorization": "Bearer " + TOKEN},
        max_size=4 << 20,
    ) as ws:
        started = time.perf_counter()
        await ws.send(
            json.dumps(
                {
                    "type": "start",
                    "mode": "text" if mode == "text" else "",
                    "text": "What makes a system reliable?",
                    "sample_rate": 16000,
                    "audio": base64.b64encode(pcm).decode(),
                }
            )
        )
        first_token = first_audio = None
        interrupted = False
        deadline = started + 80
        while time.perf_counter() < deadline:
            event = json.loads(await asyncio.wait_for(ws.recv(), timeout=80))
            event["client_ms"] = (time.perf_counter() - started) * 1000
            if event.get("audio"):
                raw = base64.b64decode(event.pop("audio"))
                event["audio_bytes"] = len(raw)
                event["audio_sha256"] = hashlib.sha256(raw).hexdigest()
            events.append(event)
            if event["type"] == "token" and event.get("text") and first_token is None:
                first_token = event["client_ms"]
                if interrupt:
                    await ws.send(json.dumps({"type": "interrupt"}))
                    interrupted = True
            if event["type"] == "audio" and first_audio is None:
                first_audio = event["client_ms"]
            if event["type"] == "cancelled":
                assert interrupted and event["generation"] == 2
                # Keep this socket open and start a replacement turn; any stale event is a failure.
                await ws.send(
                    json.dumps(
                        {
                            "type": "start",
                            "mode": "text",
                            "text": "Say hello.",
                            "sample_rate": 16000,
                            "audio": "",
                        }
                    )
                )
                while True:
                    replacement = json.loads(await asyncio.wait_for(ws.recv(), timeout=80))
                    assert replacement["generation"] == 3, replacement
                    if replacement["type"] == "error":
                        raise AssertionError(replacement)
                    if replacement["type"] == "done":
                        break
                return {
                    "mode": mode,
                    "interrupted": True,
                    "replacement_completed": True,
                    "no_stale_frames_after_ack": True,
                    "events": events,
                }
            if event["type"] == "error":
                raise AssertionError(event)
            if event["type"] == "done":
                assert first_audio is not None
                return {
                    "mode": mode,
                    "first_token_ms": first_token,
                    "first_audio_ms": first_audio,
                    "total_ms": event["client_ms"],
                    "events": events,
                }
    raise RuntimeError("turn did not finish")


def worker(port: int, tokens: int, logs: list[Any]) -> subprocess.Popen[bytes]:
    output = (OUT / f"worker-{port}-{tokens}.log").open("wb")
    logs.append(output)
    return subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "worker.app:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--no-access-log",
        ],
        cwd=ROOT,
        env={**ENV, "PULSE_MAX_TOKENS": str(tokens)},
        stdout=output,
        stderr=subprocess.STDOUT,
    )


async def campaign() -> None:
    OUT.mkdir(exist_ok=True, parents=True)
    processes: list[subprocess.Popen[bytes]] = []
    logs: list[Any] = []
    result: dict[str, Any] = {
        "scope": (
            "actual CPU models through Go WebSocket gateway; "
            "no GPU/vLLM/container restore measurement"
        ),
        "clock": (
            "client monotonic from start-frame send after WebSocket upgrade "
            "to first received audio frame"
        ),
        "model": "HuggingFaceTB/SmolLM2-135M-Instruct",
        "asr": "faster-whisper tiny int8",
        "tts": "Piper en_US-lessac-low",
        "seed": 42,
        "configurations": [],
    }
    for port in (18081, 18091, 18092):
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", port)) == 0:
                raise RuntimeError(f"benchmark port {port} already in use")
    try:
        output = (OUT / "gateway-bench.log").open("wb")
        logs.append(output)
        gateway = subprocess.Popen(
            [str(ROOT / "bin/pulse")], cwd=ROOT, env=ENV, stdout=output, stderr=subprocess.STDOUT
        )
        processes.append(gateway)
        result["gateway_process_ready_ms"] = wait_health(18081)
        for tokens in (32, 8):
            a = worker(18091, tokens, logs)
            b = worker(18092, tokens, logs)
            processes.extend([a, b])
            readiness = [wait_health(18091), wait_health(18092)]
            cold = await turn()
            warm_fallback = None
            # Warm the secondary separately; this is not steady-state.
            a.terminate()
            a.wait(timeout=10)
            warm_fallback = await turn()
            a = worker(18091, tokens, logs)
            processes.append(a)
            wait_health(18091)
            await asyncio.sleep(3.2)
            await turn()
            config: dict[str, Any] = {
                "max_new_tokens": tokens,
                "process_ready_ms": readiness,
                "cold_first_turn": cold,
                "fallback_warmup": warm_fallback,
                "loads": [],
            }
            for concurrency in (1, 2, 4):
                rows = []
                for _ in range(2):
                    rows.extend(await asyncio.gather(*(turn() for _ in range(concurrency))))
                audio = [r["first_audio_ms"] for r in rows]
                ttft = [r["first_token_ms"] for r in rows]
                config["loads"].append(
                    {
                        "concurrency": concurrency,
                        "samples": len(rows),
                        "first_audio_p50_ms": quantile(audio, 0.5),
                        "first_audio_p99_ms": quantile(audio, 0.99),
                        "ttft_p50_ms": quantile(ttft, 0.5),
                        "ttft_p99_ms": quantile(ttft, 0.99),
                        "rows": rows,
                    }
                )
                print(
                    json.dumps({k: v for k, v in config["loads"][-1].items() if k != "rows"}),
                    flush=True,
                )
            if tokens == 8:
                config["voice_rows"] = [await turn("audio") for _ in range(3)]
                config["barge_in"] = await turn(interrupt=True)
                a.kill()
                a.wait(timeout=10)
                config["real_backend_kill"] = {
                    "signal": "SIGKILL",
                    "primary_exit": a.returncode,
                    "surviving_turn": await turn(),
                }
                assert any(
                    e.get("backend") == "worker-2" and e["type"] == "audio"
                    for e in config["real_backend_kill"]["surviving_turn"]["events"]
                )
            result["configurations"].append(config)
            for proc in (a, b):
                if proc.poll() is None:
                    proc.terminate()
                    proc.wait(timeout=10)
            await asyncio.sleep(3.2)
        (OUT / "model-bench.json").write_text(json.dumps(result, indent=2) + "\n")
        print(
            "Saved actual CPU load, public-speech, interruption and backend-kill evidence.",
            flush=True,
        )
    finally:
        for proc in processes:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
        for log in logs:
            log.close()


if __name__ == "__main__":
    asyncio.run(campaign())
