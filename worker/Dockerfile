FROM python:3.13-slim-bookworm
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libsndfile1 libgomp1 && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml ./
COPY worker worker
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir .
COPY scripts scripts
RUN mkdir -p docs/results
RUN python scripts/fetch_models.py
ENV PULSE_MODELS=/app/.cache OMP_NUM_THREADS=2
CMD ["uvicorn","worker.app:app","--host","0.0.0.0","--port","8090","--no-access-log"]
