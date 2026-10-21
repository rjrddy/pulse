# Interview drill

1. Why Go at the gateway? Its context cancellation, goroutines and HTTP stack make the ownership boundary explicit; Python handles model ecosystem dependencies.
2. Where is the cancellation linearization point? The generation increment under the socket writer mutex; an acknowledgement follows it.
3. Can already played speech be undone? No. The browser stops queued sources; the gateway fences future frames only.
4. Why not retry after audio? The user could hear repeated speech. A partial failure is visible instead.
5. Does client cancellation trip a breaker? No; it releases a probe without penalizing the backend.
6. Can a stale completion close a new circuit? Breaker tickets carry epochs. A completion from before opening is ignored.
7. What is a half-open stampede? Concurrent callers probing an unavailable service; the mutex permits one probe per breaker epoch.
8. What if a client stops reading? A socket write deadline bounds the blockage. Bounded worker queues prevent unlimited event buffering.
9. What exactly is TTFT? The saved client interval from sending a text start frame after upgrade to the first nonempty token preview.
10. What exactly is TTFA? The same boundary to the first audio frame received, not the speaker's audible output.
11. Why distinguish speech and text tests? Text skips VAD/ASR, so merging their latency distributions would hide the actual pipeline cost.
12. Are small-sample p99 values capacity guarantees? No; raw counts and interpolated quantiles are disclosed.
13. What makes inference cancellation difficult? Native ASR can finish after HTTP cancellation. The worker keeps its slot until completion and drops its output.
14. How do you prevent cross-session data leaks? Isolated worker events, bearer-authenticated worker HTTP, per-turn gateway IDs, and no audio/text journal. Tenant isolation is not implemented.
15. How is the journal crash safe? Successful fsync precedes the terminal acknowledgement. A partial line causes a deliberate startup failure rather than silent data loss.
16. Can multiple gateway replicas share that file? No; move to transactional external storage before scaling replicas.
17. Why isn't this called vLLM throughput? The measured path is Transformers on CPU; the optional vLLM adapter is explicitly unmeasured.
18. What is the configuration tradeoff? A smaller output-token cap reduces speech and model work. It does not prove a faster model at equal answer length or quality.
19. What failure is outside the experiment? Simultaneous host loss, network partitions after audible output, database replication and container restore.
20. What would you optimize first? Measure queue wait and prompt-length distributions, then evaluate batching and GPU serving under a fixed output/quality workload.
