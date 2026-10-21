# Demonstration

Start the local stack and open the console. Sign in with the password from the ignored .env. Send a text prompt and watch actual token fragments and stage timings. Play the public speech sample; it passes energy VAD, real Whisper, the language model and Piper. Interrupt during queued playback. The browser stops audio sources and the gateway acknowledges a new generation. Send a replacement prompt and inspect the completed durable history.

The automated script `scripts/browser_check.py` performs this flow in a real Chromium browser, records the screen, checks no stale generation follows the interruption acknowledgement, verifies replacement completion, and captures desktop/mobile screenshots. Set PULSE_PASSWORD in the process environment; optional CHROMIUM_PATH selects a local browser. Install Playwright Chromium and its recording dependencies first. The script retains a recording of the requested demonstration length and ffprobe independently reports its actual duration in docs/results/demo-probe.json.

Recording contains actual local model events. The public website labels it recorded evidence; no live telemetry or invented requests are presented.
