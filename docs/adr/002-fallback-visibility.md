# Retry before visible audio
Context: retrying after audible speech repeats words.
Options: retry every failed stream; never retry; retry only before audio.
Decision: token/transcript previews can be reset by an attempt-reset event. Once an audio frame is sent, the turn fails rather than silently replaying it. Client cancellation is excluded from circuit failure counts. Breaker epochs prevent old completions releasing a newer half-open probe.
Tradeoffs: some turns fail after partial speech. This protects against repetition rather than promising uninterrupted speech through every failure. The current worker sends complete synthesized sentence chunks, so TTS time-to-first-frame is not phoneme streaming.
