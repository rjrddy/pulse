"""Download public/open models to an ignored cache; no credentials required."""

import json
import urllib.request
from pathlib import Path

from huggingface_hub import snapshot_download

root = Path(".cache")
root.mkdir(exist_ok=True)
assets = {
    "jfk.flac": "https://raw.githubusercontent.com/openai/whisper/main/tests/jfk.flac",
    "en_US-lessac-low.onnx": "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/low/en_US-lessac-low.onnx",
    "en_US-lessac-low.onnx.json": "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/low/en_US-lessac-low.onnx.json",
    "PIPER_MODEL_CARD": "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/low/MODEL_CARD",
}
for name, url in assets.items():
    path = root / name
    if not path.exists():
        urllib.request.urlretrieve(url, path)
for name, repo in [
    ("whisper-tiny", "Systran/faster-whisper-tiny"),
    ("smollm", "HuggingFaceTB/SmolLM2-135M-Instruct"),
]:
    snapshot_download(repo, local_dir=root / name)
Path("docs/results/model-sources.json").write_text(
    json.dumps(
        {
            "files": assets,
            "asr": "Systran/faster-whisper-tiny",
            "llm": "HuggingFaceTB/SmolLM2-135M-Instruct",
            "tts": "rhasspy/piper-voices/en_US-lessac-low",
            "usage": "local CPU measurements; vLLM/GPU not measured",
        },
        indent=2,
    )
    + "\n"
)
