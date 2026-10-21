"""Fresh worker process/readiness/first-response timing; container restore is unmeasured."""

import asyncio
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import httpx


async def main() -> None:
    rows = []
    token = "synthetic-cold-lab-token-123456789"
    env = {
        **os.environ,
        "PULSE_TOKEN": token,
        "PULSE_MAX_TOKENS": "8",
        "TOKENIZERS_PARALLELISM": "false",
    }
    for i in range(3):
        log = Path(f"docs/results/cold-worker-{i}.log").open("wb")
        started = time.perf_counter()
        proc = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "worker.app:app",
                "--host",
                "127.0.0.1",
                "--port",
                "18100",
                "--no-access-log",
            ],
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        try:
            for _ in range(200):
                try:
                    urllib.request.urlopen("http://127.0.0.1:18100/health", timeout=0.2).close()
                    break
                except OSError:
                    await asyncio.sleep(0.05)
            else:
                raise RuntimeError("readiness deadline exceeded")
            ready = (time.perf_counter() - started) * 1000
            async with httpx.AsyncClient(timeout=60) as client:
                async with client.stream(
                    "POST",
                    "http://127.0.0.1:18100/stream",
                    headers={"Authorization": "Bearer " + token},
                    json={"mode": "text", "text": "Say hello."},
                ) as response:
                    response.raise_for_status()
                    first = None
                    async for line in response.aiter_lines():
                        event = json.loads(line)
                        assert event["type"] != "error", event
                        if event["type"] == "audio" and first is None:
                            first = (time.perf_counter() - started) * 1000
                    assert first
            rows.append(
                {
                    "ready_ms": ready,
                    "process_start_to_first_audio_ms": first,
                    "first_response_total_ms": (time.perf_counter() - started) * 1000,
                }
            )
        finally:
            proc.terminate()
            proc.wait(timeout=10)
            log.close()
    Path("docs/results/cold-start.json").write_text(
        json.dumps(
            {
                "scope": "fresh worker processes; warm filesystem/model cache; direct HTTP",
                "container_start": "not measured",
                "container_restore": "not measured",
                "samples": len(rows),
                "rows": rows,
            },
            indent=2,
        )
        + "\n"
    )
    print(json.dumps(rows, indent=2))


asyncio.run(main())
