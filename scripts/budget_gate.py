"""Fail on measured first-audio p99 exceeding an explicitly selected budget."""

import argparse
import json
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument("--tokens", type=int, required=True)
p.add_argument("--concurrency", type=int, default=4)
p.add_argument("--budget-ms", type=float, required=True)
a = p.parse_args()
result = json.loads(Path("docs/results/model-bench.json").read_text())
config = next(c for c in result["configurations"] if c["max_new_tokens"] == a.tokens)
row = next(r for r in config["loads"] if r["concurrency"] == a.concurrency)
passed = row["first_audio_p99_ms"] <= a.budget_ms
print(
    json.dumps(
        {
            "passed": passed,
            "max_new_tokens": a.tokens,
            "concurrency": a.concurrency,
            "budget_ms": a.budget_ms,
            "measured_p99_ms": row["first_audio_p99_ms"],
            "samples": row["samples"],
            "source": "model-bench.json",
        },
        indent=2,
    )
)
raise SystemExit(0 if passed else 1)
