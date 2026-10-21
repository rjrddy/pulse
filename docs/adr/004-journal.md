# Single-process durable timing journal
Context: turn history must survive local service restarts without retaining speech.
Options: in-memory history; external Postgres; a flushed append-only journal.
Decision: the gateway serializes journal writes and fsyncs before final acknowledgement. Only timing, ID, backend and outcome are saved. Startup rejects malformed records; recent history is bounded in memory.
Tradeoffs: no replication, multi-writer coordination, retention or repair automation. A crash during append can leave a partial line and require explicit operator recovery. This is a single-replica Docker-volume design. A stateless hosted runtime needs an external persistence adapter before it can claim equivalent durability.
