import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Yes Coach! — Concept",
  description:
    "Concept overview of Yes Coach!, a real-time AI coaching overlay for League of Legends.",
};

const FEATURES = [
  {
    title: "Live Game State",
    tag: "Riot Live Client API",
    body: "Polls your live game every cycle — champion stats, KDA, gold, CS, level, game clock — and compresses it into a token-cheap snapshot before anything hits the model.",
  },
  {
    title: "Proactive Checkpoints",
    tag: "checkpoints.py",
    body: "The coach speaks up on its own: fixed game-clock marks, computed objective spawns (first drake at 5:00, baron at 20:00, respawn timers) pre-warned ~30 seconds ahead, and event triggers like death streaks.",
  },
  {
    title: "Minimap Vision",
    tag: "OpenCV",
    body: "A computer-vision pass crops the minimap, masks champion blips by color, and emits a one-line map summary every poll — zero token cost. Full minimap images go to the model only when a decision truly needs them.",
  },
  {
    title: "Trend Deltas",
    tag: "trends.py",
    body: "Local, pure-function trend derivation over stored snapshots. Gemini sees deltas — “cs/min fell 7.2 → 4.1” — instead of raw history, keeping per-call cost flat over a 40-minute game.",
  },
  {
    title: "Rune Autopilot",
    tag: "LCU API",
    body: "In champ select, the coach recommends a loadout by name, fuzzy-resolves names to Riot perk IDs, and applies it to a dedicated “Yes Coach” rune page — never touching your saved pages.",
  },
  {
    title: "Session Memory",
    tag: "SQLite",
    body: "Coaching history persists across games. The coach remembers your last match and carries that context forward, so advice compounds instead of resetting every queue.",
  },
];

const FLOW = [
  {
    step: "01",
    title: "Place your button",
    body: "On launch, a dimmed crosshair overlay appears. Click once to pin the “Ask Coach!!” button anywhere on screen.",
  },
  {
    step: "02",
    title: "Hover to activate",
    body: "Hover the button and a radial bloom fills. Hold until full — no clicks mid-teamfight, no focus stolen from the game.",
  },
  {
    step: "03",
    title: "Tabs unfurl",
    body: "Three suggested-question tabs bloom out on the left, and a free-form prompt tab on the right for anything else.",
  },
  {
    step: "04",
    title: "Get coached",
    body: "Live game state, map summary, and trends are compressed and sent to Gemini. Macro advice lands in seconds, in-overlay.",
  },
];

const PIPELINE = [
  { label: "Riot Live Client", sub: "game state @ :2999" },
  { label: "LCU", sub: "lobby · champ select" },
  { label: "Minimap CV", sub: "OpenCV blip masking" },
  { label: "Compress + Trends", sub: "snapshots → deltas" },
  { label: "Gemini", sub: "coaching intelligence" },
  { label: "PyQt6 Overlay", sub: "always-on-top UI" },
];

function GoldDivider() {
  return (
    <div className="mx-auto flex w-full max-w-5xl items-center gap-4 px-6">
      <div className="h-px flex-1 bg-gradient-to-r from-transparent via-hextech-gold/40 to-hextech-gold/70" />
      <div className="h-2 w-2 rotate-45 border border-hextech-gold/70" />
      <div className="h-px flex-1 bg-gradient-to-l from-transparent via-hextech-gold/40 to-hextech-gold/70" />
    </div>
  );
}

function OverlayMock() {
  return (
    <div className="relative mx-auto aspect-[16/10] w-full max-w-xl overflow-hidden rounded-xl border border-hextech-gold/25 bg-gradient-to-br from-[#0a1428] via-[#091428] to-[#04080f] shadow-[0_0_60px_-15px_rgba(200,170,110,0.35)]">
      {/* faux game HUD */}
      <div className="absolute left-4 top-4 font-mono text-[10px] text-hextech-gold/60">
        21:47 &nbsp;|&nbsp; 7/2/11 &nbsp;|&nbsp; 184 CS &nbsp;|&nbsp; 12.3k
      </div>
      <div className="absolute right-4 top-4 h-16 w-16 rounded border border-hextech-teal/30 bg-hextech-teal/5">
        <div className="absolute left-2 top-3 h-1.5 w-1.5 rounded-full bg-red-400/80" />
        <div className="absolute left-6 top-8 h-1.5 w-1.5 rounded-full bg-red-400/80" />
        <div className="absolute bottom-2 right-3 h-1.5 w-1.5 rounded-full bg-sky-400/80" />
        <div className="absolute bottom-4 left-3 h-1.5 w-1.5 rounded-full bg-emerald-400/80" />
      </div>

      {/* left suggestion tabs */}
      <div className="absolute left-4 top-1/2 flex -translate-y-1/2 flex-col gap-2">
        {["What now?", "Fight or farm?", "Objective call"].map((t) => (
          <div
            key={t}
            className="rounded-r-md border border-hextech-teal/40 bg-hextech-teal/10 px-3 py-1.5 text-xs text-hextech-teal"
          >
            {t}
          </div>
        ))}
      </div>

      {/* right prompt tab */}
      <div className="absolute right-4 top-1/2 -translate-y-1/2 rounded-l-md border border-hextech-gold/40 bg-hextech-gold/10 px-3 py-1.5 text-xs text-hextech-gold">
        Ask anything…
      </div>

      {/* central Ask Coach button with bloom */}
      <div className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2">
        <div className="absolute inset-0 -m-6 animate-pulse rounded-full bg-hextech-gold/10 blur-xl" />
        <div className="relative flex h-24 w-24 items-center justify-center rounded-full border-2 border-hextech-gold bg-[#0a1428] text-center text-sm font-bold text-hextech-gold-bright shadow-[0_0_30px_-5px_rgba(200,170,110,0.6)]">
          Ask
          <br />
          Coach!!
        </div>
      </div>

      {/* coach reply toast */}
      <div className="absolute bottom-4 left-1/2 w-[85%] -translate-x-1/2 rounded-md border border-hextech-gold/25 bg-black/60 px-4 py-2.5 text-xs leading-relaxed text-hextech-gold-bright/90 backdrop-blur">
        <span className="font-semibold text-hextech-teal">Coach:</span> Drake
        spawns in 30s and three enemies just showed top — rotate now, ping your
        jungler, and take the free Infernal.
      </div>
    </div>
  );
}

export default function ConceptPage() {
  return (
    <main className="min-h-screen">
      {/* Hero */}
      <section className="relative overflow-hidden px-6 pb-20 pt-24">
        <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_top,rgba(10,200,185,0.08),transparent_60%)]" />
        <div className="relative mx-auto grid max-w-6xl items-center gap-12 lg:grid-cols-2">
          <div>
            <p className="mb-4 text-xs font-semibold uppercase tracking-[0.3em] text-hextech-teal">
              Concept &nbsp;·&nbsp; Real-Time AI Coaching
            </p>
            <h1 className="text-5xl font-extrabold leading-tight tracking-tight text-hextech-gold-bright sm:text-6xl">
              Yes{" "}
              <span className="bg-gradient-to-r from-hextech-gold to-hextech-gold-bright bg-clip-text text-transparent">
                Coach!
              </span>
            </h1>
            <p className="mt-6 max-w-lg text-lg leading-relaxed text-hextech-gold-bright/70">
              A transparent, always-on-top overlay that watches your League of
              Legends game live and coaches you on the fly — objective timers,
              macro calls, rune pages, and trend-aware advice, without ever
              alt-tabbing.
            </p>
            <div className="mt-8 flex flex-wrap gap-4">
              <a
                href="#how-it-works"
                className="rounded-md border border-hextech-gold bg-hextech-gold/10 px-6 py-3 text-sm font-semibold text-hextech-gold transition hover:bg-hextech-gold/20"
              >
                See how it works
              </a>
              <a
                href="#architecture"
                className="rounded-md border border-hextech-teal/50 px-6 py-3 text-sm font-semibold text-hextech-teal transition hover:bg-hextech-teal/10"
              >
                Under the hood
              </a>
            </div>
            <div className="mt-10 flex flex-wrap gap-2 text-[11px] text-hextech-gold-bright/50">
              {["Python", "PyQt6", "Riot Live Client API", "LCU", "OpenCV", "Gemini"].map(
                (t) => (
                  <span
                    key={t}
                    className="rounded-full border border-white/10 px-3 py-1"
                  >
                    {t}
                  </span>
                )
              )}
            </div>
          </div>
          <OverlayMock />
        </div>
      </section>

      <GoldDivider />

      {/* How it works */}
      <section id="how-it-works" className="px-6 py-20">
        <div className="mx-auto max-w-6xl">
          <h2 className="text-center text-3xl font-bold text-hextech-gold-bright">
            How it works
          </h2>
          <p className="mx-auto mt-3 max-w-xl text-center text-sm text-hextech-gold-bright/60">
            Designed to live inside your game, not next to it. Everything is
            hover-driven so your hands never leave the fight.
          </p>
          <div className="mt-12 grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
            {FLOW.map((f) => (
              <div
                key={f.step}
                className="rounded-lg border border-white/10 bg-white/[0.03] p-6 transition hover:border-hextech-gold/40"
              >
                <div className="font-mono text-2xl font-bold text-hextech-gold/60">
                  {f.step}
                </div>
                <h3 className="mt-3 font-semibold text-hextech-gold-bright">
                  {f.title}
                </h3>
                <p className="mt-2 text-sm leading-relaxed text-hextech-gold-bright/60">
                  {f.body}
                </p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <GoldDivider />

      {/* Features */}
      <section className="px-6 py-20">
        <div className="mx-auto max-w-6xl">
          <h2 className="text-center text-3xl font-bold text-hextech-gold-bright">
            What the coach actually knows
          </h2>
          <p className="mx-auto mt-3 max-w-xl text-center text-sm text-hextech-gold-bright/60">
            Not a chatbot with a hotkey — a pipeline that fuses live API data,
            computer vision, and game history before a single token is spent.
          </p>
          <div className="mt-12 grid gap-6 md:grid-cols-2 lg:grid-cols-3">
            {FEATURES.map((f) => (
              <div
                key={f.title}
                className="group rounded-lg border border-white/10 bg-gradient-to-b from-white/[0.04] to-transparent p-6 transition hover:border-hextech-teal/40"
              >
                <div className="flex items-center justify-between">
                  <h3 className="font-semibold text-hextech-gold-bright">
                    {f.title}
                  </h3>
                  <span className="rounded border border-hextech-teal/30 px-2 py-0.5 font-mono text-[10px] text-hextech-teal/80">
                    {f.tag}
                  </span>
                </div>
                <p className="mt-3 text-sm leading-relaxed text-hextech-gold-bright/60">
                  {f.body}
                </p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <GoldDivider />

      {/* Architecture */}
      <section id="architecture" className="px-6 py-20">
        <div className="mx-auto max-w-6xl">
          <h2 className="text-center text-3xl font-bold text-hextech-gold-bright">
            Under the hood
          </h2>
          <p className="mx-auto mt-3 max-w-xl text-center text-sm text-hextech-gold-bright/60">
            A strict Model–View–Controller overlay running at ~60fps, fed by a
            polling pipeline that keeps token cost flat no matter how long the
            game runs.
          </p>

          <div className="mt-12 flex flex-wrap items-center justify-center gap-3">
            {PIPELINE.map((p, i) => (
              <div key={p.label} className="flex items-center gap-3">
                <div className="rounded-md border border-hextech-gold/30 bg-hextech-gold/5 px-4 py-3 text-center">
                  <div className="text-sm font-semibold text-hextech-gold-bright">
                    {p.label}
                  </div>
                  <div className="mt-0.5 font-mono text-[10px] text-hextech-gold-bright/50">
                    {p.sub}
                  </div>
                </div>
                {i < PIPELINE.length - 1 && (
                  <span className="text-hextech-teal/60">→</span>
                )}
              </div>
            ))}
          </div>

          <div className="mx-auto mt-12 grid max-w-4xl gap-6 sm:grid-cols-3">
            {[
              {
                name: "Model",
                file: "model.py",
                body: "Pure state: button position, hover-fill progress, the idle → filling → unfurled → closing → cooldown state machine. No PyQt, no logic.",
              },
              {
                name: "View",
                file: "view.py",
                body: "Renders each frame purely from model state and reports on-screen button geometry back for hit-testing. Never mutates the model.",
              },
              {
                name: "Controller",
                file: "controller.py",
                body: "Owns the per-frame tick: reads the cursor against reported geometry, runs the state machine, and mutates the model.",
              },
            ].map((m) => (
              <div
                key={m.name}
                className="rounded-lg border border-white/10 bg-white/[0.03] p-5"
              >
                <div className="flex items-baseline justify-between">
                  <h3 className="font-semibold text-hextech-teal">{m.name}</h3>
                  <span className="font-mono text-[10px] text-hextech-gold-bright/40">
                    {m.file}
                  </span>
                </div>
                <p className="mt-2 text-sm leading-relaxed text-hextech-gold-bright/60">
                  {m.body}
                </p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-white/10 px-6 py-10">
        <div className="mx-auto flex max-w-6xl flex-col items-center justify-between gap-4 text-xs text-hextech-gold-bright/40 sm:flex-row">
          <span>
            Yes Coach! — concept page. Requires Python 3.10+, a live League
            game, and a Gemini API key.
          </span>
          <span className="font-mono">
            gemini-2.0-flash &nbsp;·&nbsp; macOS &nbsp;·&nbsp; ~60fps overlay
          </span>
        </div>
      </footer>
    </main>
  );
}
