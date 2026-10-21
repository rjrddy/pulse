# Native inference owns its admission slot
Context: cancelling a Python coroutine does not interrupt a C/C++ inference call.
Options: release on HTTP disconnect; kill a process per turn; bound native work and suppress disconnected output.
Decision: a semaphore bounds active/queued inference; a single inference executor serializes each worker's model use. The native producer releases its slot only after inference returns. A bounded event queue applies streaming backpressure and a stop flag prevents writes after disconnect.
Tradeoffs: an interrupted ASR operation can delay the replacement turn. Native model execution is cooperative, not hard real-time preemption. Independent worker processes contain crashes but not host failures.
