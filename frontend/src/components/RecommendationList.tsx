import { motion } from "framer-motion";
import { useQuery, useQueryClient, useMutation } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api, type ActionLogEntry, type Recommendation } from "../api";
import { useAuth } from "../auth/AuthContext";

const SEVERITY_STYLE: Record<string, string> = {
  critical: "border-red-400/40 bg-red-400/10 text-red-300",
  warning: "border-amber-400/40 bg-amber-400/10 text-amber-300",
  info: "border-cyan-400/40 bg-cyan-400/10 text-cyan-300",
};

export default function RecommendationList({ limit }: { limit?: number }) {
  const { hasRole } = useAuth();
  const queryClient = useQueryClient();
  const canAct = hasRole("admin", "controller");

  const { data, isLoading } = useQuery<Recommendation[]>({
    queryKey: ["recommendations"],
    queryFn: async () => (await api.get("/api/recommendations")).data,
  });

  const { data: log } = useQuery<ActionLogEntry[]>({
    queryKey: ["action-log"],
    queryFn: async () => (await api.get("/api/recommendations/log")).data,
    enabled: canAct,
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

  const items = limit ? data?.slice(0, limit) : data;

  return (
    <div className="glass rounded-2xl p-4">
      <div className="flex items-center justify-between mb-3">
        <h2 className="font-semibold text-slate-200">AI Controller Recommendations</h2>
        {data && <span className="text-xs text-slate-400">{data.length} active</span>}
      </div>
      {isLoading && <div className="text-sm text-slate-400">Loading...</div>}
      {!isLoading && (!items || items.length === 0) && (
        <div className="text-sm text-slate-400">
          All trains running within normal tolerances. No action required.
        </div>
      )}
      <div className="flex flex-col gap-2">
        {items?.map((r, i) => {
          const done = actionedIds.has(`${r.train_number}-${r.station_code}`);
          return (
            <motion.div
              key={r.id}
              initial={{ opacity: 0, x: -8 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: i * 0.04 }}
              className={`rounded-xl border px-3 py-2 text-sm ${SEVERITY_STYLE[r.severity]}`}
            >
              <div className="flex items-center justify-between gap-2">
                <Link to={`/trains/${r.train_number}`} className="font-mono font-semibold hover:underline">
                  {r.train_number}
                </Link>
                <span className="text-xs uppercase tracking-wide opacity-80">{r.severity}</span>
              </div>
              <div className="text-slate-200 mt-1">{r.message}</div>
              <div className="text-xs text-slate-400 mt-1 flex items-center justify-between gap-2">
                <span>→ {r.suggested_action}</span>
                {canAct && (
                  <button
                    disabled={done || apply.isPending}
                    onClick={() => apply.mutate(r.id)}
                    className="rounded-lg px-2 py-1 text-xs font-semibold bg-white/10 hover:bg-white/20 disabled:opacity-40 whitespace-nowrap"
                  >
                    {done ? "Actioned" : "Apply"}
                  </button>
                )}
              </div>
              <div className="text-[10px] text-slate-500 mt-1">
                prediction source: {r.prediction_source}
              </div>
            </motion.div>
          );
        })}
      </div>
    </div>
  );
}
