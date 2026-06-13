import { useState } from "react";
import { useNavigate } from "react-router-dom";
import type { TwinSnapshot } from "../api";
import CorridorSchematic from "../components/CorridorSchematic";
import StationInfoCard from "../components/StationInfoCard";
import { motion, AnimatePresence } from "framer-motion";

const SEVERITY_COLOR = (delay: number | null) => {
  if (delay == null) return "text-slate-400";
  if (delay >= 30) return "text-red-400";
  if (delay >= 10) return "text-amber-400";
  return "text-emerald-400";
};

export default function Twin({ snapshot }: { snapshot: TwinSnapshot | null }) {
  const navigate = useNavigate();
  const [selectedStation, setSelectedStation] = useState<string | null>(null);
  const running = snapshot?.trains.filter((t) => t.status === "running") ?? [];

  return (
    <div className="flex flex-col gap-5">
      <div>
        <h1 className="text-2xl font-bold text-gradient">Digital Twin — NDLS ⇄ CNB Corridor</h1>
        <p className="text-sm text-slate-400">
          {snapshot ? new Date(snapshot.sim_time).toLocaleString("en-IN") : "Connecting..."} ·
          simulation speed {snapshot?.sim_speed ?? "–"}x
        </p>
      </div>

      <div className="glass-strong rounded-2xl p-4 glow-cyan">
        {snapshot ? (
          <CorridorSchematic
            stations={snapshot.stations}
            trains={snapshot.trains}
            onSelectTrain={(t) => navigate(`/trains/${t}`)}
            onSelectStation={(s) => setSelectedStation((cur) => (cur === s ? null : s))}
            selectedStation={selectedStation}
          />
        ) : (
          <div className="text-sm text-slate-400 py-16 text-center">Connecting to twin feed...</div>
        )}
        <AnimatePresence>
          {snapshot && selectedStation && (
            <StationInfoCard
              station={snapshot.stations.find((s) => s.station_code === selectedStation)!}
              trains={snapshot.trains}
              onClose={() => setSelectedStation(null)}
            />
          )}
        </AnimatePresence>
      </div>

      <div className="glass rounded-2xl p-4">
        <h2 className="font-semibold text-slate-200 mb-3">Trains in Section ({running.length})</h2>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-slate-400 text-xs uppercase tracking-wide">
                <th className="py-2 pr-3">Train</th>
                <th className="py-2 pr-3">Type</th>
                <th className="py-2 pr-3">Direction</th>
                <th className="py-2 pr-3">Section</th>
                <th className="py-2 pr-3">Current Delay</th>
                <th className="py-2 pr-3">Predicted Next</th>
                <th className="py-2 pr-3">ETA Next</th>
              </tr>
            </thead>
            <tbody>
              {running.map((t, i) => (
                <motion.tr
                  key={t.train_number}
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  transition={{ delay: i * 0.02 }}
                  className="border-t border-white/5 hover:bg-white/5 cursor-pointer"
                  onClick={() => navigate(`/trains/${t.train_number}`)}
                >
                  <td className="py-2 pr-3 font-mono font-semibold">{t.train_number}</td>
                  <td className="py-2 pr-3">{t.train_type}</td>
                  <td className="py-2 pr-3 text-xs">{t.corridor_direction}</td>
                  <td className="py-2 pr-3">
                    {t.from_station} → {t.to_station}{" "}
                    <span className="text-slate-500">({Math.round(t.progress * 100)}%)</span>
                  </td>
                  <td className={`py-2 pr-3 font-mono ${SEVERITY_COLOR(t.current_delay)}`}>
                    {t.current_delay.toFixed(0)}m
                  </td>
                  <td className={`py-2 pr-3 font-mono ${SEVERITY_COLOR(t.predicted_delay_next)}`}>
                    {t.predicted_delay_next?.toFixed(0) ?? "–"}m
                    <span className="text-[10px] text-slate-500 ml-1">({t.prediction_source})</span>
                  </td>
                  <td className="py-2 pr-3 text-xs text-slate-400">
                    {t.eta_next ? new Date(t.eta_next).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" }) : "–"}
                  </td>
                </motion.tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
