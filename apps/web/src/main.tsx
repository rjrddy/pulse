import "./motion";
import React, { useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import "./style.css";
type Frame = {
  type: string;
  generation: number;
  stage?: string;
  duration_ms?: number;
  text?: string;
  audio?: string;
  sample_rate?: number;
  elapsed_ms: number;
  backend?: string;
  error?: string;
  attempt?: number;
};
type Status = {
  backends: Record<string, string>;
  active: number;
  turns: number;
  failures: number;
  fallbacks: number;
  budget_ms: number;
};
type Turn = {
  id: string;
  outcome: string;
  backend: string;
  first_audio_ms: number;
  total_ms: number;
  at: string;
};
function App() {
  const [ready, setReady] = useState(false),
    [password, setPassword] = useState(""),
    [error, setError] = useState(""),
    [status, setStatus] = useState<Status | null>(null),
    [history, setHistory] = useState<Turn[]>([]),
    [state, setState] = useState("Idle"),
    [transcript, setTranscript] = useState(""),
    [reply, setReply] = useState(""),
    [prompt, setPrompt] = useState("What makes a system reliable?"),
    [frames, setFrames] = useState<Frame[]>([]),
    [first, setFirst] = useState<number | null>(null),
    [busy, setBusy] = useState(false),
    [playing, setPlaying] = useState(false);
  const socket = useRef<WebSocket | null>(null),
    generation = useRef(0),
    audio = useRef<AudioContext | null>(null),
    sources = useRef<AudioBufferSourceNode[]>([]),
    next = useRef(0),
    started = useRef(0),
    observed = useRef(false);
  const stopAudio = () => {
    for (const source of sources.current) {
      try {
        source.stop();
      } catch {
        /* Already ended */
      }
    }
    sources.current = [];
    setPlaying(false);
    next.current = 0;
  };
  const refresh = async () => {
    try {
      const res = await fetch("/api/status");
      if (res.status === 401) {
        setReady(false);
        return;
      }
      if (!res.ok) throw Error("Status unavailable");
      setStatus(await res.json());
      setReady(true);
      const h = await fetch("/api/history");
      if (h.ok) setHistory((await h.json()).reverse());
    } catch (e) {
      setError(String(e));
    }
  };
  useEffect(() => {
    void refresh();
    const id = setInterval(() => void refresh(), 2000);
    return () => {
      clearInterval(id);
      socket.current?.close();
      stopAudio();
      void audio.current?.close();
    };
  }, []);
  const connect = async () => {
    if (socket.current?.readyState === WebSocket.OPEN) return socket.current;
    return new Promise<WebSocket>((resolve, reject) => {
      const ws = new WebSocket(
        `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/api/stream`,
      );
      socket.current = ws;
      generation.current = 0;
      ws.onopen = () => resolve(ws);
      ws.onerror = () => reject(Error("Streaming connection failed"));
      ws.onclose = () => {
        setBusy(false);
        setState("Disconnected");
      };
      ws.onmessage = ({ data }) => {
        const event = JSON.parse(data) as Frame;
        if (event.generation !== generation.current) return;
        setFrames((rows) => [...rows.slice(-149), event]);
        if (event.type === "transcript") setTranscript(event.text ?? "");
        if (event.type === "token")
          setReply((text) => text + (event.text ?? ""));
        if (event.type === "attempt_reset") {
          setReply("");
          setTranscript("");
          setState("Falling back");
        }
        if (event.type === "stage") setState(event.stage ?? "Processing");
        if (event.type === "audio" && event.audio) {
          setState("Speaking");
          setPlaying(true);
          if (!observed.current) {
            observed.current = true;
            setFirst(performance.now() - started.current);
          }
          const ctx = audio.current;
          if (ctx) {
            const bytes = Uint8Array.from(atob(event.audio), (c) =>
                c.charCodeAt(0),
              ),
              pcm = new Int16Array(bytes.buffer),
              buffer = ctx.createBuffer(
                1,
                pcm.length,
                event.sample_rate ?? 22050,
              );
            buffer
              .getChannelData(0)
              .set(Float32Array.from(pcm, (x) => x / 32768));
            const source = ctx.createBufferSource();
            source.buffer = buffer;
            source.connect(ctx.destination);
            const when = Math.max(ctx.currentTime + 0.025, next.current);
            source.start(when);
            next.current = when + buffer.duration;
            sources.current.push(source);
            source.onended = () => {
              sources.current = sources.current.filter((s) => s !== source);
              if (!sources.current.length) setPlaying(false);
            };
          }
        }
        if (event.type === "done") {
          setBusy(false);
          setState("Complete");
          void refresh();
        }
        if (event.type === "error") {
          setBusy(false);
          setState("Failed");
          setError(event.error ?? "Turn failed");
        }
        if (event.type === "cancelled") {
          setBusy(false);
          setState("Interrupted");
        }
      };
    });
  };
  const start = async (mode: "audio" | "text") => {
    try {
      setError("");
      audio.current ??= new AudioContext();
      await audio.current.resume();
      const ws = await connect();
      stopAudio();
      generation.current++;
      const thisGeneration = generation.current;
      setFrames([]);
      setReply("");
      setTranscript("");
      setFirst(null);
      observed.current = false;
      setBusy(true);
      setState("Processing");
      let encoded = "";
      if (mode === "audio") {
        const res = await fetch("/sample/sample.pcm");
        if (!res.ok) throw Error("Public sample not available");
        const data = new Uint8Array(await res.arrayBuffer());
        let binary = "";
        for (const b of data) binary += String.fromCharCode(b);
        encoded = btoa(binary);
      }
      if (thisGeneration !== generation.current) return;
      started.current = performance.now();
      ws.send(
        JSON.stringify({
          type: "start",
          mode: mode === "text" ? "text" : "",
          text: prompt,
          audio: encoded,
          sample_rate: 16000,
        }),
      );
    } catch (e) {
      setBusy(false);
      setError(String(e));
    }
  };
  const interrupt = () => {
    generation.current++;
    stopAudio();
    socket.current?.send(JSON.stringify({ type: "interrupt" }));
    setBusy(false);
    setState("Interrupted");
  };
  const login = async (e: React.FormEvent) => {
    e.preventDefault();
    const r = await fetch("/api/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ password }),
    });
    if (!r.ok) {
      setError("Sign-in failed. Check your password or wait before retrying.");
      return;
    }
    setPassword("");
    setError("");
    void refresh();
  };
  return (
    <>
      <header>
        <a className="brand" href="/">
          <span className="pulse-symbol" aria-hidden="true">
            ◉
          </span>{" "}
          pulse
        </a>
        <span className="headerlabel">VOICE SYSTEM / SESSION INSTRUMENT</span>
        <a href="https://github.com/rjrddy/pulse">Source ↗</a>
      </header>
      <main>
        <div className="heading">
          <div>
            <p className="eyebrow">THE LISTENING ROOM</p>
            <h1>Every stage has a deadline.</h1>
            <p className="intro">
              Follow a voice turn from speech to first audio. Interrupt it.
              Watch the gateway fence stale output and route around failure.
            </p>
          </div>
          <span className={ready ? "badge" : "badge offline"}>
            {ready ? "● Gateway connected" : "○ Sign in to connect"}
          </span>
        </div>
        {error && (
          <div className="error" role="alert">
            {error}
          </div>
        )}
        {!ready ? (
          <form onSubmit={login} className="login">
            <h2>Connect to your gateway</h2>
            <p>
              Use the operator password configured in your local .env. Audio is
              processed transiently; history stores timing and outcomes.
            </p>
            <label>
              Operator password
              <input
                type="password"
                required
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </label>
            <button>Sign in →</button>
          </form>
        ) : (
          <>
            <div className="stats">
              {[
                [status?.turns ?? 0, "Turns observed"],
                [status?.active ?? 0, "Active sessions"],
                [status?.fallbacks ?? 0, "Fallback attempts"],
                [`${status?.budget_ms ?? 0} ms`, "Turn budget"],
              ].map(([v, k]) => (
                <div key={String(k)}>
                  <strong>{v}</strong>
                  <span>{k}</span>
                </div>
              ))}
            </div>
            <div className="grid">
              <section className="panel session-deck">
                <div className="sectiontitle">
                  <h2>Voice session</h2>
                  <span className="badge">{state}</span>
                </div>
                <div
                  className={
                    "instrument-display " + (playing ? "is-playing" : "")
                  }
                  role="status"
                  aria-label="Audio transport status"
                >
                  <div className="transport-disc" aria-hidden="true">
                    <span>p</span>
                  </div>
                  <div className="transport-readout">
                    <span>OUTPUT / PCM</span>
                    <strong>
                      {playing ? "PLAYING" : busy ? "PROCESSING" : "STANDBY"}
                    </strong>
                    <small>
                      {first === null
                        ? "First audio not observed"
                        : `First audio received in ${first.toFixed(1)} ms`}
                    </small>
                  </div>
                  <div className="transport-lights" aria-hidden="true">
                    {["vad", "asr", "llm", "tts"].map((s) => (
                      <i
                        key={s}
                        className={
                          frames.some(
                            (f) => f.type === "stage" && f.stage === s,
                          )
                            ? "lit"
                            : ""
                        }
                      >
                        {s}
                      </i>
                    ))}
                  </div>
                </div>
                <p className="muted">
                  Use the public Whisper speech sample, or a text prompt to
                  isolate LLM → TTS. No microphone recording is saved.
                </p>
                <label>
                  Text prompt
                  <input
                    value={prompt}
                    maxLength={800}
                    onChange={(e) => setPrompt(e.target.value)}
                  />
                </label>
                <div className="actions">
                  <button disabled={busy} onClick={() => void start("audio")}>
                    ▶ Public speech sample
                  </button>
                  <button
                    className="secondary"
                    disabled={busy}
                    onClick={() => void start("text")}
                  >
                    Send text
                  </button>
                  <button
                    className="danger"
                    disabled={!busy && !playing}
                    onClick={interrupt}
                  >
                    ■ Interrupt
                  </button>
                </div>
                <div className="conversation">
                  <p className="eyebrow">TRANSCRIPT</p>
                  <p>{transcript || "Waiting for a turn…"}</p>
                  <p className="eyebrow">MODEL RESPONSE</p>
                  <p aria-live="polite">
                    {reply || "Tokens will appear as they arrive."}
                  </p>
                </div>
                <div className="first">
                  <span>Client-observed time to first audio</span>
                  <strong>
                    {first === null ? "—" : `${first.toFixed(1)} ms`}
                  </strong>
                </div>
                <p className="muted">
                  Audio-frame arrival includes gateway transport. Playback may
                  start later. This is an observed turn, not a percentile.
                </p>
              </section>
              <section className="panel">
                <div className="sectiontitle">
                  <h2>Latency waterfall</h2>
                  <span>Actual worker stages</span>
                </div>
                <div className="stages">
                  {["vad", "asr", "llm", "tts"].map((stage) => {
                    const f = frames
                      .filter((f) => f.type === "stage" && f.stage === stage)
                      .at(-1);
                    return (
                      <div className="stage" key={stage}>
                        <span>{stage.toUpperCase()}</span>
                        <div className="track">
                          <div
                            style={{
                              width: f
                                ? `${Math.max(2, Math.min(100, (f.duration_ms ?? 0) / ((status?.budget_ms ?? 40000) / 100)))}%`
                                : "0%",
                            }}
                          />
                        </div>
                        <code>
                          {f ? `${f.duration_ms?.toFixed(1)} ms` : "—"}
                        </code>
                      </div>
                    );
                  })}
                </div>
                <h3>Backend health</h3>
                {Object.entries(status?.backends ?? {}).map(([name, state]) => (
                  <div className="backend" key={name}>
                    <span>{name}</span>
                    <span className={state === "closed" ? "ok" : "warn"}>
                      {state === "closed" ? "Circuit closed" : "Circuit open"}
                    </span>
                  </div>
                ))}
                <p className="muted">
                  A closed circuit permits work; it is not a successful health
                  probe. Fallback stops after audio becomes visible.
                </p>
                <h3>Event trace</h3>
                <div className="eventlog" role="log">
                  {frames.map((f, i) => (
                    <div key={i}>
                      <time>{f.elapsed_ms?.toFixed(1) ?? "0"} ms</time>
                      <span>
                        {f.type}
                        {f.stage ? ` / ${f.stage}` : ""}
                      </span>
                      <span>{f.backend ?? `generation ${f.generation}`}</span>
                    </div>
                  ))}
                  {!frames.length && (
                    <p className="muted">Start a turn to see real events.</p>
                  )}
                </div>
              </section>
            </div>
            <section className="panel">
              <div className="sectiontitle">
                <h2>Durable turn history</h2>
                <span>Outcome and timings only · no audio or text</span>
              </div>
              <div className="tablewrap">
                <table>
                  <thead>
                    <tr>
                      <th>Turn / trace</th>
                      <th>Outcome</th>
                      <th>Backend</th>
                      <th>First audio</th>
                      <th>Total</th>
                    </tr>
                  </thead>
                  <tbody>
                    {history.map((t) => (
                      <tr key={t.id}>
                        <td>
                          <code>{t.id}</code>
                        </td>
                        <td>{t.outcome}</td>
                        <td>{t.backend}</td>
                        <td>
                          {t.first_audio_ms
                            ? t.first_audio_ms.toFixed(1) + " ms"
                            : "not observed"}
                        </td>
                        <td>{t.total_ms.toFixed(1)} ms</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {!history.length && (
                <p className="muted">
                  Completed turns appear here after the journal is flushed.
                </p>
              )}
            </section>
          </>
        )}
        <footer>
          <span>Real CPU models · Synthetic and public data only</span>
          <a href="https://github.com/rjrddy/pulse/blob/main/docs/DESIGN.md">
            Guarantees and limits ↗
          </a>
        </footer>
      </main>
    </>
  );
}
createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
