"""Measure one real-model turn against an already running Compose deployment."""

import asyncio
import json
import os
from pathlib import Path
import time
from websockets.asyncio.client import connect


async def main() -> None:
    base = os.getenv("PULSE_SMOKE_WS", "ws://127.0.0.1:8081/api/stream")
    events = []
    started = time.perf_counter()
    async with connect(
        base,
        additional_headers={"Authorization": "Bearer " + os.environ["PULSE_TOKEN"]},
        max_size=4 << 20,
    ) as ws:
        await ws.send(
            json.dumps(
                {
                    "type": "start",
                    "mode": "text",
                    "sample_rate": 16000,
                    "text": "Say hello.",
                    "audio": "",
                }
            )
        )
        while True:
            event = json.loads(await asyncio.wait_for(ws.recv(), timeout=90))
            event.pop("audio", None)
            events.append(event)
            if event["type"] == "error":
                raise AssertionError(event)
            if event["type"] == "done":
                break
    assert any(e["type"] == "audio" for e in events)
    Path("docs/results/compose-smoke.json").write_text(
        json.dumps(
            {
                "events": events,
                "elapsed_ms": (time.perf_counter() - started) * 1000,
                "real_models": True,
            },
            indent=2,
        )
        + "\n"
    )


asyncio.run(main())
