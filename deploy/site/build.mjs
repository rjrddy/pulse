import { mkdirSync, readFileSync, writeFileSync, copyFileSync } from "node:fs";
const dest = "deploy/site/dist";
mkdirSync(dest, { recursive: true });
for (const name of ["index.html", "style.css", "app.js"])
  copyFileSync("deploy/site/" + name, dest + "/" + name);
const read = (name) => JSON.parse(readFileSync("docs/results/" + name, "utf8"));
writeFileSync(
  dest + "/proof.json",
  JSON.stringify({
    bench: read("model-bench.json"),
    checks: read("checks.json"),
    domain: read("domain-eval.json"),
    cold: read("cold-start.json"),
    recording: read("ui-redesign/demo-probe.json"),
  }),
);
for (const name of ["demo.webm", "console-desktop.png", "model-bench.json"])
  copyFileSync(
    name === "demo.webm"
      ? "docs/results/ui-redesign/demo.webm"
      : name === "console-desktop.png"
        ? "docs/results/ui-redesign/console-cover.png"
        : "docs/results/" + name,
    dest + "/" + name,
  );
console.log(
  "Built recorded evidence from actual CPU-model measurements. Live gateway is not hosted.",
);
