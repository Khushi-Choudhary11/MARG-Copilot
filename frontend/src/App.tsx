import { Navigate, NavLink, Route, Routes, useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import Dashboard from "./pages/Dashboard";
import Twin from "./pages/Twin";
import Trains from "./pages/Trains";
import TrainDetail from "./pages/TrainDetail";
import Analytics from "./pages/Analytics";
import Controller from "./pages/Controller";
import Login from "./pages/Login";
import Landing from "./pages/Landing";
import ProtectedRoute from "./auth/ProtectedRoute";
import AiAssistant from "./components/AiAssistant";
import { useAuth } from "./auth/AuthContext";
import { useTwinSnapshot } from "./hooks/useTwinSnapshot";

const NAV = [
  { to: "/", label: "Dashboard", icon: "◆" },
  { to: "/twin", label: "Digital Twin", icon: "◎" },
  { to: "/trains", label: "Trains", icon: "▤" },
  { to: "/analytics", label: "Analytics", icon: "▦" },
];

const CONTROLLER_NAV = { to: "/controller", label: "Controller", icon: "⚙" };

function App() {
  const { snapshot, connected } = useTwinSnapshot();
  const { user, logout, hasRole } = useAuth();
  const navigate = useNavigate();

  const navItems = hasRole("admin", "controller") ? [...NAV, CONTROLLER_NAV] : NAV;

  if (!user) {
    return (
      <Routes>
        <Route path="/" element={<Landing />} />
        <Route path="/login" element={<Login />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    );
  }

  return (
    <div className="flex min-h-screen w-full">
      <aside className="hidden md:flex w-60 flex-col border-r border-white/5 glass-strong px-4 py-6 gap-6">
        <div>
          <div className="text-lg font-bold text-gradient">NDLS ⇄ CNB</div>
          <div className="text-xs text-slate-400 mt-1">Railway Digital Twin</div>
        </div>
        <nav className="flex flex-col gap-1">
          {navItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                `flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors ${
                  isActive
                    ? "bg-white/10 text-cyan-300 font-medium"
                    : "text-slate-400 hover:bg-white/5 hover:text-slate-200"
                }`
              }
            >
              <span className="text-base">{item.icon}</span>
              {item.label}
            </NavLink>
          ))}
        </nav>
        <div className="mt-auto text-xs text-slate-500 space-y-3">
          <div className="flex items-center gap-2">
            <span
              className={`h-2 w-2 rounded-full ${
                connected ? "bg-emerald-400 pulse-dot" : "bg-red-400"
              }`}
            />
            {connected ? "Live feed connected" : "Reconnecting..."}
          </div>
          {snapshot && (
            <div className="font-mono text-slate-400">
              Sim: {new Date(snapshot.sim_time).toLocaleString("en-IN", {
                hour: "2-digit",
                minute: "2-digit",
                day: "2-digit",
                month: "short",
              })}
            </div>
          )}
          <div className="rounded-xl glass px-3 py-2">
            <div className="text-slate-200 font-semibold">{user.name}</div>
            <div className="capitalize text-cyan-400">{user.role}</div>
            <button
              onClick={() => {
                logout();
                navigate("/");
              }}
              className="mt-2 w-full rounded-lg px-2 py-1 bg-white/5 hover:bg-white/10 text-slate-300"
            >
              Log out
            </button>
          </div>
        </div>
      </aside>

      <div className="flex-1 flex flex-col min-w-0">
        <header className="md:hidden glass-strong px-4 py-3 flex items-center justify-between">
          <div className="font-bold text-gradient">NDLS ⇄ CNB Digital Twin</div>
          <div className="flex items-center gap-3">
            <span className={`h-2 w-2 rounded-full ${connected ? "bg-emerald-400" : "bg-red-400"}`} />
            <button onClick={logout} className="text-xs text-slate-400">Log out</button>
          </div>
        </header>
        <motion.main
          className="flex-1 p-4 md:p-6 overflow-y-auto"
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.35 }}
        >
          <Routes>
            <Route path="/" element={<Dashboard snapshot={snapshot} />} />
            <Route path="/twin" element={<Twin snapshot={snapshot} />} />
            <Route path="/trains" element={<Trains />} />
            <Route path="/trains/:trainNumber" element={<TrainDetail />} />
            <Route path="/analytics" element={<Analytics />} />
            <Route
              path="/controller"
              element={
                <ProtectedRoute roles={["admin", "controller"]}>
                  <Controller />
                </ProtectedRoute>
              }
            />
          </Routes>
        </motion.main>
      </div>

      {/* Bottom nav for mobile */}
      <nav className="md:hidden fixed bottom-0 left-0 right-0 glass-strong flex justify-around py-2 z-50">
        {navItems.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            className={({ isActive }) =>
              `flex flex-col items-center text-xs gap-1 px-2 ${
                isActive ? "text-cyan-300" : "text-slate-400"
              }`
            }
          >
            <span className="text-lg">{item.icon}</span>
            {item.label}
          </NavLink>
        ))}
      </nav>

      <AiAssistant />
    </div>
  );
}

export default App;
