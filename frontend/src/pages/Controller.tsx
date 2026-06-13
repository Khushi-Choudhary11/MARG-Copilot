import { useQuery, useQueryClient, useMutation } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { api, type ActionLogEntry, type Recommendation } from "../api";
import { useAuth } from "../auth/AuthContext";

const SEVERITY_STYLE: Record<string, string> = {
  critical: "border-red-400/40 bg-red-400/10 text-red-300",
  warning: "border-amber-400/40 bg-amber-400/10 text-amber-300",
  info: "border-cyan-400/40 bg-cyan-400/10 text-cyan-300",
};

export default function Controller() {
  const { hasRole } = useAuth();
  const queryClient = useQueryClient();
  const canAct = hasRole("admin", "controller");

  const { data: status } = useQuery<{ auto_mode: boolean }>({
    queryKey: ["controller-status"],
    queryFn: async () => (await api.get("/api/controller/status")).data,
    refetchInterval: 4000,
  });

  const { data: recs } = useQuery<Recommendation[]>({
    queryKey: ["recommendations"],
    queryFn: async () => (await api.get("/api/recommendations")).data,
    refetchInterval: 4000,
  });

  const { data: log } = useQuery<ActionLogEntry[]>({
    queryKey: ["action-log"],
    queryFn: async () => (await api.get("/api/recommendations/log")).data,
    refetchInterval: 4000,
  });

  const toggleAuto = useMutation({
    mutationFn: async (enabled: boolean) =>
      (await api.post("/api/controller/auto-mode", { enabled })).data,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["controller-status"] }),
  });

  const apply = useMutation({
    mutationFn: async (id: string) => (await api.post(`/api/recommendations/${id}/apply`)).data,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["action-log"] });
      queryClient.invalidateQueries({ queryKey: ["recommendations"] });
    },
  });

  const actionedIds = new Set<string>();
  for (const entry of log ?? []) {
    actionedIds.add(`${entry.train_number}-${entry.station_code}`);
  }

  return (
    <div className="flex flex-col gap-5">
      <div>
        <h1 className="text-2xl font-bold text-gradient">Controller Console</h1>
        <p className="text-sm text-slate-400">
          Apply AI recommendations or enable Auto-Controller to act on critical alerts automatically.
        </p>
      </div>

      <div className="glass rounded-2xl p-4 flex items-center justify-between">
        <div>
          <div className="font-semibold text-slate-200">Auto-Controller Mode</div>
          <div className="text-xs text-slate-400">
            When enabled, critical recommendations are automatically logged as actioned.
          </div>
        </div>
        <button
          disabled={!canAct}
          onClick={() => toggleAuto.mutate(!status?.auto_mode)}
          className={`relative w-16 h-8 rounded-full transition-colors ${
            status?.auto_mode ? "bg-emerald-500/60" : "bg-slate-600/60"
          } disabled:opacity-50`}
        >
          <motion.div
            className="absolute top-1 h-6 w-6 rounded-full bg-white"
            animate={{ left: status?.auto_mode ? 36 : 4 }}
            transition={{ type: "spring", stiffness: 400, damping: 25 }}
          />
        </button>
      </div>

      <div className="glass rounded-2xl p-4">
        <h2 className="font-semibold text-slate-200 mb-3">Active Recommendations</h2>
        <div className="flex flex-col gap-2">
          {recs?.length === 0 && <div className="text-sm text-slate-400">No active recommendations.</div>}
          {recs?.map((r) => {
            const key = `${r.train_number}-${r.station_code}`;
            const done = actionedIds.has(key);
            return (
              <div key={r.id} className={`rounded-xl border px-3 py-2 text-sm ${SEVERITY_STYLE[r.severity]} flex items-center gap-3`}>
                <div className="flex-1">
                  <div className="font-mono font-semibold">{r.train_number}</div>
                  <div className="text-slate-200">{r.message}</div>
                  <div className="text-xs text-slate-400 mt-1">→ {r.suggested_action}</div>
                </div>
                <button
                  disabled={!canAct || done}
                  onClick={() => apply.mutate(r.id)}
                  className="rounded-lg px-3 py-1.5 text-xs font-semibold bg-white/10 hover:bg-white/20 disabled:opacity-40 whitespace-nowrap"
                >
                  {done ? "Actioned" : "Apply"}
                </button>
              </div>
            );
          })}
        </div>
      </div>

      <div className="glass rounded-2xl p-4">
        <h2 className="font-semibold text-slate-200 mb-3">Action Log</h2>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-slate-400 text-xs uppercase tracking-wide">
                <th className="py-2 pr-3">Time</th>
                <th className="py-2 pr-3">Train</th>
                <th className="py-2 pr-3">Station</th>
                <th className="py-2 pr-3">Severity</th>
                <th className="py-2 pr-3">Action</th>
                <th className="py-2 pr-3">By</th>
              </tr>
            </thead>
            <tbody>
              {log?.map((entry) => (
                <tr key={entry.id} className="border-t border-white/5">
                  <td className="py-2 pr-3 text-xs text-slate-400">
                    {new Date(entry.timestamp).toLocaleTimeString("en-IN")}
                  </td>
                  <td className="py-2 pr-3 font-mono">{entry.train_number}</td>
                  <td className="py-2 pr-3">{entry.station_code}</td>
                  <td className="py-2 pr-3 capitalize">{entry.severity}</td>
                  <td className="py-2 pr-3 text-xs text-slate-300">{entry.action}</td>
                  <td className="py-2 pr-3 text-xs">
                    {entry.actor} {entry.auto && <span className="text-cyan-400">(auto)</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {(!log || log.length === 0) && <div className="text-sm text-slate-400 py-4">No actions logged yet.</div>}
        </div>
      </div>
    </div>
  );
}
