"""Convert the public Whisper test clip into transient benchmark PCM."""

import os
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy.signal import resample_poly

root = Path(os.getenv("PULSE_SAMPLE_OUT", "/public"))
root.mkdir(parents=True, exist_ok=True)
audio, rate = sf.read(".cache/jfk.flac", dtype="float32")
audio = resample_poly(audio, 16000, rate)[: 16000 * 10]
(root / "sample.pcm").write_bytes((np.clip(audio, -1, 1) * 32767).astype("<i2").tobytes())
