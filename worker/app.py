"""Real CPU/open-model worker with bounded admission and cancellable streaming."""

from __future__ import annotations

import asyncio
import base64
import contextlib
import json
import logging
import os
import threading
import time
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import numpy as np
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

log = logging.getLogger("pulse.worker")
app = FastAPI(title="Pulse open-model worker")
slots = threading.BoundedSemaphore(2)
executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="inference")
models: Models | None = None


class VoiceInput(BaseModel):
    audio: str = Field(default="", max_length=900000)
    sample_rate: int = 16000
    mode: str = ""
    text: str = Field(default="", max_length=800)


def voice_region(pcm: np.ndarray, threshold: float = 0.009) -> np.ndarray:
    """Energy VAD trims leading/trailing quiet frames, keeping interior pauses."""
    if len(pcm) < 320:
        raise ValueError("audio too short")
    frames = [pcm[i : i + 320] for i in range(0, len(pcm), 320)]
    active = [i for i, f in enumerate(frames) if np.sqrt(np.mean(f * f)) >= threshold]
    if not active:
        raise ValueError("no speech energy detected")
    start = max(0, active[0] - 2) * 320
    end = min(len(pcm), (active[-1] + 3) * 320)
    return pcm[start:end]


class Models:
    def __init__(self, root: Path) -> None:
        import torch
        from faster_whisper import WhisperModel
        from piper import PiperVoice
        from transformers import AutoModelForCausalLM, AutoTokenizer

        torch.manual_seed(42)
        torch.set_num_threads(int(os.getenv("PULSE_TORCH_THREADS", "2")))
        self.asr = WhisperModel(str(root / "whisper-tiny"), device="cpu", compute_type="int8")
        self.tts = PiperVoice.load(str(root / "en_US-lessac-low.onnx"))
        self.vllm_url = os.getenv("PULSE_VLLM_URL", "")
        if not self.vllm_url:
            self.tokenizer = AutoTokenizer.from_pretrained(root / "smollm", local_files_only=True)
            self.llm = AutoModelForCausalLM.from_pretrained(root / "smollm", local_files_only=True)
            self.llm.eval()

    def tokens(self, text: str, stop: threading.Event) -> Iterator[str]:
        if self.vllm_url:
            import httpx

            with httpx.stream(
                "POST",
                self.vllm_url.rstrip("/") + "/v1/chat/completions",
                json={
                    "model": os.environ["PULSE_VLLM_MODEL"],
                    "stream": True,
                    "max_tokens": 32,
                    "temperature": 0,
                    "messages": [{"role": "user", "content": text}],
                },
                timeout=25,
            ) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    if stop.is_set() or line == "data: [DONE]":
                        break
                    if line.startswith("data: "):
                        yield json.loads(line[6:])["choices"][0]["delta"].get("content", "")
            return
        import torch
        from transformers import StoppingCriteria, StoppingCriteriaList, TextIteratorStreamer

        class Cancel(StoppingCriteria):
            def __call__(self, *_: Any, **__: Any) -> bool:
                return stop.is_set()

        messages = [{"role": "user", "content": "Answer briefly in one sentence: " + text}]
        prompt = self.tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
        inputs = self.tokenizer(prompt, return_tensors="pt")
        streamer = TextIteratorStreamer(
            self.tokenizer, skip_prompt=True, skip_special_tokens=True, timeout=30
        )
        failure: list[Exception] = []

        def generate() -> None:
            try:
                with torch.inference_mode():
                    self.llm.generate(
                        **inputs,
                        streamer=streamer,
                        max_new_tokens=int(os.getenv("PULSE_MAX_TOKENS", "32")),
                        do_sample=False,
                        stopping_criteria=StoppingCriteriaList([Cancel()]),
                        pad_token_id=self.tokenizer.eos_token_id,
                    )
            except Exception as exc:
                failure.append(exc)
                streamer.end()

        thread = threading.Thread(target=generate, daemon=True)
        thread.start()
        try:
            yield from streamer
        finally:
            stop.set() if failure else None
            thread.join(timeout=30)
        if failure:
            raise RuntimeError("language model inference failed") from failure[0]

    def pipeline(self, data: VoiceInput, stop: threading.Event) -> Iterator[dict[str, Any]]:
        started = time.perf_counter()
        if data.mode == "text":
            text = data.text
        else:
            pcm = np.frombuffer(base64.b64decode(data.audio, validate=True), dtype="<i2")
            if data.sample_rate != 16000 or not 320 <= len(pcm) <= 320000:
                raise ValueError("requires mono PCM16 at 16000 Hz, up to twenty seconds")
            pcm = voice_region(pcm.astype(np.float32) / 32768)
            yield {
                "type": "stage",
                "stage": "vad",
                "duration_ms": (time.perf_counter() - started) * 1000,
            }
            if stop.is_set():
                return
            started = time.perf_counter()
            segments, _ = self.asr.transcribe(pcm, beam_size=1, language="en", vad_filter=False)
            text = " ".join(s.text.strip() for s in segments)
            yield {
                "type": "stage",
                "stage": "asr",
                "duration_ms": (time.perf_counter() - started) * 1000,
            }
        if stop.is_set():
            return
        yield {"type": "transcript", "text": text}
        started = time.perf_counter()
        reply: list[str] = []
        for token in self.tokens(text, stop):
            if stop.is_set():
                return
            reply.append(token)
            yield {"type": "token", "text": token}
        yield {
            "type": "stage",
            "stage": "llm",
            "duration_ms": (time.perf_counter() - started) * 1000,
        }
        if stop.is_set():
            return
        started = time.perf_counter()
        for chunk in self.tts.synthesize("".join(reply).strip() or "Please try again."):
            if stop.is_set():
                return
            yield {
                "type": "audio",
                "audio": base64.b64encode(chunk.audio_int16_bytes).decode(),
                "sample_rate": chunk.sample_rate,
            }
        yield {
            "type": "stage",
            "stage": "tts",
            "duration_ms": (time.perf_counter() - started) * 1000,
        }
        yield {"type": "done"}


def load_models() -> Models:
    global models
    if models is None:
        models = Models(Path(os.getenv("PULSE_MODELS", ".cache")))
    return models


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "models_loaded": models is not None,
        "llm": "vllm" if os.getenv("PULSE_VLLM_URL") else "transformers-cpu",
    }


@app.post("/stream")
async def stream(
    data: VoiceInput, request: Request, authorization: str | None = Header(default=None)
) -> StreamingResponse:
    import secrets

    token = os.getenv("PULSE_TOKEN", "")
    if len(token) < 24 or not secrets.compare_digest(authorization or "", "Bearer " + token):
        raise HTTPException(401, "worker authentication required")
    if data.mode not in ("", "text") or (data.mode == "text" and not data.text.strip()):
        raise HTTPException(422, "invalid mode or empty text")
    if not slots.acquire(blocking=False):
        raise HTTPException(503, "worker capacity reached")
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue(maxsize=8)
    stop = threading.Event()

    def put(event: dict[str, Any] | None) -> bool:
        if stop.is_set():
            return False
        future = asyncio.run_coroutine_threadsafe(queue.put(event), loop)
        while not stop.is_set():
            try:
                future.result(timeout=0.2)
                return True
            except TimeoutError:
                pass
        future.cancel()
        return False

    def produce() -> None:
        try:
            for event in load_models().pipeline(data, stop):
                if not put(event):
                    break
        except Exception as exc:
            log.error(json.dumps({"event": "inference_failed", "kind": type(exc).__name__}))
            put({"type": "error", "error": "inference failed"})
        finally:
            slots.release()  # The native inference thread, not disconnected HTTP, owns this slot.
            put(None)

    try:
        executor.submit(produce)
    except Exception:
        slots.release()
        raise

    async def events() -> Any:
        try:
            while True:
                event = await queue.get()
                if event is None:
                    break
                if await request.is_disconnected():
                    break
                yield json.dumps(event) + "\n"
        finally:
            stop.set()
            with contextlib.suppress(asyncio.QueueEmpty):
                while True:
                    queue.get_nowait()

    return StreamingResponse(events(), media_type="application/x-ndjson")
