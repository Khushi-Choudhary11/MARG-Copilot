import { useState } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { motion } from "framer-motion";
import { useAuth } from "../auth/AuthContext";

const DEMO_ACCOUNTS = [
  { role: "Admin", username: "admin", password: "admin123" },
  { role: "Controller", username: "controller", password: "controller123" },
  { role: "Viewer", username: "viewer", password: "viewer123" },
];

export default function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const from = (location.state as { from?: string })?.from ?? "/";

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await login(username, password);
      navigate(from, { replace: true });
    } catch {
      setError("Invalid username or password");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center p-4">
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        className="glass-strong rounded-2xl p-8 w-full max-w-md glow-cyan"
      >
        <div className="text-center mb-6">
          <div className="text-2xl font-bold text-gradient">NDLS ⇄ CNB</div>
          <div className="text-sm text-slate-400 mt-1">Railway Digital Twin · Sign in</div>
        </div>
        <form onSubmit={handleSubmit} className="flex flex-col gap-3">
          <input
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            placeholder="Username"
            className="glass rounded-xl px-4 py-2 text-sm outline-none focus:ring-2 focus:ring-cyan-400/40"
            autoFocus
          />
          <input
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            type="password"
            placeholder="Password"
            className="glass rounded-xl px-4 py-2 text-sm outline-none focus:ring-2 focus:ring-cyan-400/40"
          />
          {error && <div className="text-sm text-red-400">{error}</div>}
          <button
            type="submit"
            disabled={loading}
            className="mt-2 rounded-xl px-4 py-2 text-sm font-semibold bg-gradient-to-r from-cyan-500 to-violet-500 text-slate-900 hover:opacity-90 transition-opacity disabled:opacity-50"
          >
            {loading ? "Signing in..." : "Sign in"}
          </button>
        </form>

        <div className="mt-6 text-xs text-slate-400">
          <div className="mb-2 uppercase tracking-wide text-slate-500">Demo accounts</div>
          <div className="grid grid-cols-1 gap-1">
            {DEMO_ACCOUNTS.map((acc) => (
              <button
                key={acc.username}
                onClick={() => {
                  setUsername(acc.username);
                  setPassword(acc.password);
                }}
                className="flex justify-between rounded-lg px-3 py-1.5 glass hover:ring-1 hover:ring-cyan-400/40 text-left"
              >
                <span className="font-medium text-slate-300">{acc.role}</span>
                <span className="font-mono">{acc.username} / {acc.password}</span>
              </button>
            ))}
          </div>
        </div>
      </motion.div>
    </div>
  );
}
