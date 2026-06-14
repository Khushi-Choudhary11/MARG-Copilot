import { useNavigate } from "react-router-dom";
import { motion } from "framer-motion";

const FEATURES = [
  {
    icon: "◎",
    title: "Live Digital Twin",
    accent: "cyan",
    body:
      "A real-time, animated map of the NDLS ⇄ CNB corridor (via GZB, ALJN, TDL, ETW) replaying a full service day on a compressed clock — every train's position, direction and delay, live.",
  },
  {
    icon: "🧠",
    title: "AI Delay Prediction",
    accent: "violet",
    body:
      "A LightGBM model trained on real running-history, weather, infrastructure and calendar features predicts each train's delay at its next station — not just a static average.",
  },
  {
    icon: "⚡",
    title: "AI Controller Recommendations",
    accent: "amber",
    body:
      "Every prediction is turned into a plain-language operational suggestion — hold, re-platform, grant priority pass — ranked by severity so controllers act on what matters first.",
  },
  {
    icon: "⚙",
    title: "Auto-Controller Mode",
    accent: "green",
    body:
      "Toggle autopilot to automatically action critical (>30 min) recommendations the instant they're detected, with a full audit trail in the Action Log.",
  },
  {
    icon: "▦",
    title: "Corridor Analytics",
    accent: "cyan",
    body:
      "Corridor-wide KPIs, delay distributions and on-time performance — the same numbers a section controller would want on a wallboard.",
  },
  {
    icon: "🤖",
    title: "AI Assistant",
    accent: "violet",
    body:
      "A built-in chat assistant (Claude-powered) answers questions about live train status, delays and recommended actions in natural language.",
  },
];

const STEPS = [
  {
    n: "01",
    title: "Watch the corridor breathe",
    body: "Open the Digital Twin and watch all 82 trains on the demo day move along the NDLS⇄CNB corridor in real time, color-coded by delay severity.",
  },
  {
    n: "02",
    title: "See AI predictions, not guesses",
    body: "Every running train gets a model-predicted delay for its next station — so controllers see problems forming before they happen.",
  },
  {
    n: "03",
    title: "Act on ranked recommendations",
    body: "The dashboard surfaces concrete suggestions ('grant priority pass through CNB', 'hold at ALJN to regularize') ordered by how critical the delay is.",
  },
  {
    n: "04",
    title: "Apply, automate, audit",
    body: "Controllers apply suggestions with one click — or flip on Auto-Controller mode and let the system action critical cases itself, fully logged.",
  },
];

const IMPACT = [
  {
    stat: "Cascading delays",
    detail:
      "Today, a single late train can ripple across an entire corridor before anyone reacts. Earlier, AI-driven visibility means earlier intervention — and fewer knock-on delays for every other service.",
  },
  {
    stat: "Controller workload",
    detail:
      "Section controllers juggle dozens of trains from memory and radio calls. A ranked, predictive worklist turns reactive firefighting into proactive traffic management.",
  },
  {
    stat: "Decision consistency",
    detail:
      "Auto-Controller mode applies the same rules every time for critical cases, day or night, shift after shift — reducing variance between individual controllers' judgment calls.",
  },
  {
    stat: "Scales beyond one corridor",
    detail:
      "The same pipeline — real running data + weather + infrastructure features + LightGBM — can be retrained and redeployed for any other Indian Railways corridor.",
  },
];

const ACCENT_CLASSES: Record<string, string> = {
  cyan: "text-cyan-400 border-cyan-400/30",
  violet: "text-violet-400 border-violet-400/30",
  amber: "text-amber-400 border-amber-400/30",
  green: "text-emerald-400 border-emerald-400/30",
  red: "text-red-400 border-red-400/30",
};

export default function Landing() {
  const navigate = useNavigate();

  return (
    <div className="min-h-screen w-full overflow-y-auto">
      {/* Hero */}
      <section className="px-4 md:px-10 pt-10 pb-16 max-w-5xl mx-auto text-center">
        <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}>
          <div className="inline-flex items-center gap-2 text-xs font-mono uppercase tracking-widest text-cyan-400/80 glass rounded-full px-3 py-1 mb-5">
            <span className="h-2 w-2 rounded-full bg-emerald-400 pulse-dot" />
            Live simulated demo · real running-history data
          </div>
          <h1 className="text-4xl md:text-6xl font-extrabold text-gradient leading-tight">
            A Digital Twin for Indian Railways' <br className="hidden md:block" />
            NDLS ⇄ CNB Corridor
          </h1>
          <p className="mt-5 text-base md:text-lg text-slate-400 max-w-3xl mx-auto">
            Watch trains move along New Delhi → Ghaziabad → Aligarh → Tundla → Etawah → Kanpur
            Central in real time, see an AI model predict delays before they happen, and let an
            AI controller assistant turn predictions into action — automatically.
          </p>
          <div className="mt-8 flex flex-col sm:flex-row items-center justify-center gap-3">
            <button
              onClick={() => navigate("/login")}
              className="rounded-xl px-6 py-3 text-sm font-semibold bg-gradient-to-r from-cyan-500 to-violet-500 text-slate-900 hover:opacity-90 transition-opacity glow-cyan"
            >
              Launch the Live Demo →
            </button>
            <a
              href="#how-it-works"
              className="rounded-xl px-6 py-3 text-sm font-semibold glass hover:ring-1 hover:ring-cyan-400/40 text-slate-200 transition"
            >
              See how it works
            </a>
          </div>
          <p className="mt-4 text-xs text-slate-500">
            No setup needed — sign in instantly with a demo Admin, Controller or Viewer account.
          </p>
        </motion.div>
      </section>

      {/* The problem */}
      <section className="px-4 md:px-10 pb-14 max-w-5xl mx-auto">
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          className="glass-strong rounded-2xl p-6 md:p-8"
        >
          <h2 className="text-xl md:text-2xl font-bold text-slate-100 mb-3">
            Why this matters
          </h2>
          <p className="text-sm md:text-base text-slate-400 leading-relaxed">
            Train delays on busy Indian corridors rarely stay isolated — a 20-minute delay at one
            station can cascade into platform conflicts, missed crossings, and hours of knock-on
            disruption across the network. Section controllers currently manage this with
            experience, radio calls and static timetables, reacting only after a delay is already
            visible. This project explores what becomes possible when controllers instead have a{" "}
            <span className="text-cyan-300 font-medium">live, predictive, simulated view</span>{" "}
            of the corridor — built entirely on real historical running data, weather and
            infrastructure information for the NDLS–CNB route.
          </p>
        </motion.div>
      </section>

      {/* Features */}
      <section className="px-4 md:px-10 pb-14 max-w-6xl mx-auto">
        <motion.h2
          initial={{ opacity: 0, y: 12 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          className="text-xl md:text-2xl font-bold text-slate-100 mb-6 text-center"
        >
          What's inside the platform
        </motion.h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {FEATURES.map((f, i) => (
            <motion.div
              key={f.title}
              initial={{ opacity: 0, y: 12 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ delay: i * 0.05 }}
              className={`glass rounded-2xl p-5 border ${ACCENT_CLASSES[f.accent]}`}
            >
              <div className={`text-2xl mb-2 ${ACCENT_CLASSES[f.accent].split(" ")[0]}`}>{f.icon}</div>
              <h3 className="font-semibold text-slate-100 mb-1.5">{f.title}</h3>
              <p className="text-sm text-slate-400 leading-relaxed">{f.body}</p>
            </motion.div>
          ))}
        </div>
      </section>

      {/* How it works */}
      <section id="how-it-works" className="px-4 md:px-10 pb-14 max-w-5xl mx-auto">
        <motion.h2
          initial={{ opacity: 0, y: 12 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          className="text-xl md:text-2xl font-bold text-slate-100 mb-6 text-center"
        >
          How it works
        </motion.h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {STEPS.map((s, i) => (
            <motion.div
              key={s.n}
              initial={{ opacity: 0, y: 12 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ delay: i * 0.06 }}
              className="glass-strong rounded-2xl p-5 flex gap-4"
            >
              <div className="text-3xl font-mono font-bold text-gradient shrink-0">{s.n}</div>
              <div>
                <h3 className="font-semibold text-slate-100 mb-1">{s.title}</h3>
                <p className="text-sm text-slate-400 leading-relaxed">{s.body}</p>
              </div>
            </motion.div>
          ))}
        </div>
      </section>

      {/* Impact */}
      <section className="px-4 md:px-10 pb-14 max-w-5xl mx-auto">
        <motion.h2
          initial={{ opacity: 0, y: 12 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          className="text-xl md:text-2xl font-bold text-slate-100 mb-2 text-center"
        >
          The impact this can have
        </motion.h2>
        <p className="text-sm text-slate-400 text-center mb-6 max-w-2xl mx-auto">
          This is a demo built on real (and calibrated) data — but the same approach maps directly
          onto operational gains for a real control office:
        </p>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {IMPACT.map((item, i) => (
            <motion.div
              key={item.stat}
              initial={{ opacity: 0, y: 12 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ delay: i * 0.06 }}
              className="glass rounded-2xl p-5"
            >
              <div className="text-sm font-semibold uppercase tracking-wide text-cyan-400 mb-2">
                {item.stat}
              </div>
              <p className="text-sm text-slate-400 leading-relaxed">{item.detail}</p>
            </motion.div>
          ))}
        </div>
      </section>

      {/* CTA / roles */}
      <section className="px-4 md:px-10 pb-16 max-w-5xl mx-auto">
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          className="glass-strong rounded-2xl p-6 md:p-8 text-center glow-cyan"
        >
          <h2 className="text-xl md:text-2xl font-bold text-slate-100 mb-2">
            Try every role — no signup required
          </h2>
          <p className="text-sm text-slate-400 mb-6 max-w-2xl mx-auto">
            Explore the platform as a read-only <span className="text-slate-200">Viewer</span>, a{" "}
            <span className="text-slate-200">Controller</span> who can apply AI recommendations
            and toggle Auto-Controller mode, or an <span className="text-slate-200">Admin</span>{" "}
            with full access to everything above.
          </p>
          <button
            onClick={() => navigate("/login")}
            className="rounded-xl px-8 py-3 text-sm font-semibold bg-gradient-to-r from-cyan-500 to-violet-500 text-slate-900 hover:opacity-90 transition-opacity"
          >
            Sign in &amp; explore →
          </button>
        </motion.div>
      </section>

      {/* Footer */}
      <footer className="px-4 md:px-10 pb-10 max-w-5xl mx-auto text-center text-xs text-slate-500">
        <p>
          NDLS ⇄ CNB Railway Digital Twin — built on real timetable, station infrastructure,
          weather and running-history data for the New Delhi → Kanpur Central corridor. Simulation
          runs on a compressed clock for demo purposes; predictions are served by a LightGBM
          delay-prediction model.
        </p>
      </footer>
    </div>
  );
}
