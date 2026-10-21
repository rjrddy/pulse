# Go owns session generations
Context: cancellation can arrive while an old worker is returning audio.
Options: let workers alone cancel; discard stale data only in the browser; fence gateway writes.
Decision: serialize generation checks and socket writes under the same mutex. Interrupt advances the generation, cancels HTTP, and acknowledges on that socket. All later frames from the old generation are rejected.
Tradeoffs: one slow socket write can delay cancellation until its bounded write deadline. Audio already received by a client cannot be recalled. The browser separately stops its scheduled audio sources.
