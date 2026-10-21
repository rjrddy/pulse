"""Protocol fixtures test bounds; these are never model benchmark evidence."""

import numpy as np
import pytest
from fastapi.testclient import TestClient

from worker.app import app, voice_region


def test_vad_preserves_interior_pause() -> None:
    pcm = np.zeros(320 * 20, dtype=np.float32)
    pcm[320 * 5 : 320 * 8] = 0.2
    pcm[320 * 12 : 320 * 15] = 0.2
    trimmed = voice_region(pcm)
    assert len(trimmed) == 320 * 14
    assert np.count_nonzero(trimmed) == 320 * 6


def test_vad_rejects_silence() -> None:
    with pytest.raises(ValueError, match="no speech"):
        voice_region(np.zeros(3200, dtype=np.float32))


def test_vad_seeded_boundaries() -> None:
    rng = np.random.default_rng(42)
    for _ in range(200):
        start = int(rng.integers(3, 30))
        end = int(rng.integers(start + 1, 40))
        audio = np.zeros(320 * 45, dtype=np.float32)
        audio[320 * start : 320 * end] = 0.1
        trimmed = voice_region(audio)
        assert np.count_nonzero(trimmed) == (end - start) * 320
        assert 0 < len(trimmed) <= len(audio)


def test_worker_auth_and_input_limits(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PULSE_TOKEN", "synthetic-worker-token-123456789")
    client = TestClient(app)
    assert client.post("/stream", json={}).status_code == 401
    auth = {"Authorization": "Bearer synthetic-worker-token-123456789"}
    assert client.post("/stream", json={"mode": "text"}, headers=auth).status_code == 422
    assert client.post("/stream", json={"text": "a" * 801}, headers=auth).status_code == 422
