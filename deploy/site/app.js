const data = await fetch("/proof.json").then((r) => {
  if (!r.ok) throw Error("Measurement data unavailable");
  return r.json();
});
const config = (cap) =>
  data.bench.configurations.find((c) => c.max_new_tokens === Number(cap));
const low = config(8).loads.find((r) => r.concurrency === 4),
  high = config(32).loads.find((r) => r.concurrency === 4);
for (const [value, label] of [
  [
    low.first_audio_p99_ms.toFixed(2) + " ms",
    "first-audio p99 / shorter output",
  ],
  [
    high.first_audio_p99_ms.toFixed(2) + " ms",
    "first-audio p99 / longer output",
  ],
  [low.samples, "samples per configuration at concurrency 4"],
  [
    data.checks.go_race_tests_passed + data.checks.python_tests_passed,
    "passing tests",
  ],
]) {
  const el = document.createElement("div");
  el.className = "metric";
  const v = document.createElement("strong");
  v.textContent = value;
  const l = document.createElement("span");
  l.textContent = label;
  el.append(v, l);
  document.querySelector("#metrics").append(el);
}
function render() {
  const body = document.querySelector("#loads");
  body.replaceChildren();
  for (const row of config(document.querySelector("#cap").value).loads) {
    const tr = document.createElement("tr");
    for (const value of [
      row.concurrency,
      row.samples,
      row.ttft_p99_ms.toFixed(2) + " ms",
      row.first_audio_p50_ms.toFixed(2) + " ms",
      row.first_audio_p99_ms.toFixed(2) + " ms",
    ]) {
      const td = document.createElement("td");
      td.textContent = value;
      tr.append(td);
    }
    body.append(tr);
  }
}
document.querySelector("#cap").addEventListener("change", render);
render();
document.querySelector("#duration").textContent =
  `Actual local screen recording · ${Number(data.recording.format.duration).toFixed(2)} seconds · No simulated live counters.`;

document.querySelector("#hero-audio").textContent =
  low.first_audio_p99_ms.toFixed(2) + " ms";
