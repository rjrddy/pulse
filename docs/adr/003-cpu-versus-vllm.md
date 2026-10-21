# Real CPU measurements and a separate vLLM adapter
Context: the development host has no CUDA GPU or Docker daemon. Fake model timings would invalidate the project.
Options: benchmark mocks; rent a GPU without authorization; run genuine small CPU models and retain explicit gaps.
Decision: faster-whisper tiny int8, Transformers SmolLM2 and Piper are the measured default. A worker can call a separately provisioned vLLM OpenAI-compatible streaming endpoint using PULSE_VLLM_URL and PULSE_VLLM_MODEL.
Tradeoffs: CPU output has limited language quality; it is not a production assistant. The adapter is not evidence of a measured vLLM deployment. GPU, vLLM and container restore remain unmeasured. No cloud GPU was purchased.
Source: https://docs.vllm.ai/en/latest/serving/openai_compatible_server.html
