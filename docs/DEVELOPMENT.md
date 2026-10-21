# Development

`python3 scripts/configure.py` creates ignored local credentials. `docker compose up --build` builds the gateway and actual CPU workers, downloads the public models, prepares the public sample, and starts the console at http://localhost:8081. Read the operator password from .env locally. Keep the two default commands; the configuration step is unnecessary if credentials already exist.

Native development: `make setup models build`, then start independent uvicorn workers on local ports, set PULSE_BACKENDS to their URLs, and start bin/pulse with the provisioned password/token. Prepare public PCM with `PULSE_SAMPLE_OUT=apps/web/dist/sample .venv/bin/python scripts/prepare_sample.py`. `make lint test bench` runs the required local gates; bench launches isolated gateway/worker subprocesses on dedicated benchmark ports and terminates only its own processes.

Python's pyproject selects model/runtime requirements. requirements.lock records the measured development environment; its dev/audit packages are not required by the inference worker. The Docker worker preinstalls CPU Torch from its official CPU index. CI installs lightweight protocol-test dependencies separately, then builds and tests the real model image in an independent clone. Long CPU sweeps run locally, not on every CI push.

For observability, export PULSE_TOKEN from your ignored environment, run scripts/prometheus_config.py, then `docker compose --profile observability up --build`. Prometheus scrapes bearer-protected metrics using an ignored credential file. Provision Grafana's Prometheus datasource as http://prometheus:9090. The console supplies stage waterfall events and per-turn trace IDs; no OTLP exporter or long-term trace backend is implemented.

To use vLLM, provision a compatible endpoint separately and set PULSE_VLLM_URL and PULSE_VLLM_MODEL on each worker. No cloud GPU or new provider account is created automatically. This adapter has no measured vLLM/GPU result in the saved campaign. See the ADR and current upstream docs: https://docs.vllm.ai/en/latest/serving/openai_compatible_server.html.

The public Vercel site is an evidence viewer with the actual screen recording. It does not launch the CPU models or persist new turns. External history and worker services must be configured before a live hosted console can claim the local journal guarantees.
