import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { api, type TrainSummary } from "../api";
import { motion } from "framer-motion";

export default function Trains() {
  const [search, setSearch] = useState("");
  const [direction, setDirection] = useState<string>("");

  const { data, isLoading } = useQuery<TrainSummary[]>({
    queryKey: ["trains", search, direction],
    queryFn: async () =>
      (
        await api.get("/api/trains", {
          params: { q: search || undefined, direction: direction || undefined },
        })
      ).data,
    refetchInterval: 15000,
  });

  return (
    <div className="flex flex-col gap-5">
      <div>
        <h1 className="text-2xl font-bold text-gradient">Trains on Corridor</h1>
        <p className="text-sm text-slate-400">Search and inspect any train's scheduled corridor run.</p>
      </div>

      <div className="flex flex-wrap gap-3">
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search train number or name..."
          className="glass rounded-xl px-4 py-2 text-sm flex-1 min-w-[220px] outline-none focus:ring-2 focus:ring-cyan-400/40"
        />
        <select
          value={direction}
          onChange={(e) => setDirection(e.target.value)}
          className="glass rounded-xl px-4 py-2 text-sm outline-none focus:ring-2 focus:ring-cyan-400/40"
        >
          <option value="">All directions</option>
          <option value="DOWN (NDLS->CNB)">DOWN (NDLS→CNB)</option>
          <option value="UP (CNB->NDLS)">UP (CNB→NDLS)</option>
        </select>
      </div>

      {isLoading && <div className="text-sm text-slate-400">Loading...</div>}

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
        {data?.map((t, i) => (
          <motion.div
            key={t.train_number}
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: Math.min(i * 0.02, 0.4) }}
          >
            <Link
              to={`/trains/${t.train_number}`}
              className="glass rounded-2xl p-4 flex flex-col gap-1 hover:ring-2 hover:ring-cyan-400/40 transition-all block h-full"
            >
              <div className="flex items-center justify-between">
                <span className="font-mono font-bold text-lg">{t.train_number}</span>
                <span className="text-xs px-2 py-0.5 rounded-full bg-white/10 text-slate-300">
                  P{t.priority}
                </span>
              </div>
              <div className="text-sm text-slate-200">{t.train_name}</div>
              <div className="text-xs text-slate-400">{t.train_type}</div>
              <div className="text-xs text-slate-500 mt-1">{t.corridor_direction}</div>
              <div className="text-xs text-slate-400 mt-2 font-mono">
                {t.stops.join(" → ")}
              </div>
            </Link>
          </motion.div>
        ))}
      </div>
      {!isLoading && data?.length === 0 && (
        <div className="text-sm text-slate-400 text-center py-8">No trains match your search.</div>
      )}
    </div>
  );
}
