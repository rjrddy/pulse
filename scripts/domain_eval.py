"""Small synthetic speech evaluation; explicitly not a held-out human-speech benchmark."""

import json
import re
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf
from faster_whisper import WhisperModel
from piper import PiperVoice
from scipy.signal import resample_poly


def words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def distance(a: list[str], b: list[str]) -> int:
    row = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        new = [i]
        for j, y in enumerate(b, 1):
            new.append(min(new[-1] + 1, row[j] + 1, row[j - 1] + (x != y)))
        row = new
    return row[-1]


def main() -> None:
    voice = PiperVoice.load(".cache/en_US-lessac-low.onnx")
    asr = WhisperModel(".cache/whisper-tiny", device="cpu", compute_type="int8")
    cases = [
        ("Postgres stores our workflow history.", "postgres"),
        ("Kubernetes restarts the failed worker.", "kubernetes"),
        ("OpenTelemetry connects the service traces.", "opentelemetry"),
    ]
    rows: list[dict[str, Any]] = []
    for i, (reference, term) in enumerate(cases):
        chunks = list(voice.synthesize(reference))
        rate = chunks[0].sample_rate
        audio = np.concatenate([np.frombuffer(c.audio_int16_bytes, dtype="<i2") for c in chunks])
        sf.write(f"docs/results/domain-{i}.wav", audio, rate, subtype="PCM_16")
        audio = resample_poly(audio.astype(np.float32) / 32768, 16000, rate)
        for hints in (False, True):
            segments, _ = asr.transcribe(
                audio,
                beam_size=1,
                language="en",
                initial_prompt="Postgres, Kubernetes, OpenTelemetry." if hints else None,
            )
            text = " ".join(s.text.strip() for s in segments)
            rows.append(
                {
                    "reference": reference,
                    "term": term,
                    "glossary_hints": hints,
                    "transcript": text,
                    "word_errors": distance(words(reference), words(text)),
                    "reference_words": len(words(reference)),
                    "term_correct": term in "".join(words(text)),
                }
            )
    result = {
        "scope": (
            "Piper-generated synthetic speech, fixed glossary; "
            "tiny development sample, not held out"
        ),
        "rows": rows,
        "aggregates": [],
    }
    for hints in (False, True):
        subset = [r for r in rows if r["glossary_hints"] == hints]
        result["aggregates"].append(
            {
                "glossary_hints": hints,
                "samples": len(subset),
                "term_accuracy": sum(r["term_correct"] for r in subset) / len(subset),
                "word_error_rate": sum(r["word_errors"] for r in subset)
                / sum(r["reference_words"] for r in subset),
            }
        )
    Path("docs/results/domain-eval.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result["aggregates"], indent=2))


if __name__ == "__main__":
    main()
