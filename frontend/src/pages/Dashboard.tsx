import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { AnimatePresence } from "framer-motion";
import { api, type KpiSummary, type TwinSnapshot } from "../api";
import KpiCard from "../components/KpiCard";
import RecommendationList from "../components/RecommendationList";
import CorridorSchematic from "../components/CorridorSchematic";
import StationInfoCard from "../components/StationInfoCard";

export default function Dashboard({ snapshot }: { snapshot: TwinSnapshot | null }) {
  const navigate = useNavigate();
  const [selectedStation, setSelectedStation] = useState<string | null>(null);
  const { data: kpis } = useQuery<KpiSummary>({
    queryKey: ["kpis"],
    queryFn: async () => (await api.get("/api/analytics/kpis")).data,
    refetchInterval: 4000,
  });

  return (
    <div className="flex flex-col gap-5">
      <div>
        <h1 className="text-2xl font-bold text-gradient">Corridor Overview</h1>
        <p className="text-sm text-slate-400">
          New Delhi ⇄ Kanpur Central · Live digital twin (simulated demo day{" "}
          {kpis?.demo_date ?? "—"})
        </p>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <KpiCard label="Trains on Corridor" value={`${kpis?.running_trains ?? "–"}`} sublabel={`of ${kpis?.total_trains ?? "–"} today`} accent="cyan" />
        <KpiCard label="Avg Current Delay" value={`${kpis?.avg_current_delay?.toFixed(1) ?? "–"} min`} accent="violet" />
        <KpiCard label="Predicted Next-Stn Delay" value={`${kpis?.avg_predicted_delay?.toFixed(1) ?? "–"} min`} accent="amber" />
        <KpiCard
          label="On Time / Delayed"
          value={`${kpis?.on_time_pct?.toFixed(0) ?? "–"}% / ${kpis?.delayed_pct?.toFixed(0) ?? "–"}%`}
          accent={kpis && kpis.delayed_pct > 50 ? "red" : "green"}
        />
      </div>

      <div className="glass rounded-2xl p-4">
        <div className="flex items-center justify-between mb-2">
          <h2 className="font-semibold text-slate-200">Live Corridor Map</h2>
          <div className="flex items-center gap-3 text-xs text-slate-400">
            <span className="flex items-center gap-1"><span className="h-2 w-2 rounded-full bg-cyan-400" />DOWN (NDLS→CNB)</span>
            <span className="flex items-center gap-1"><span className="h-2 w-2 rounded-full bg-violet-400" />UP (CNB→NDLS)</span>
          </div>
        </div>
        {snapshot ? (
          <CorridorSchematic
            stations={snapshot.stations}
            trains={snapshot.trains}
            compact
            onSelectTrain={(t) => navigate(`/trains/${t}`)}
            onSelectStation={(s) => setSelectedStation((cur) => (cur === s ? null : s))}
            selectedStation={selectedStation}
          />
        ) : (
          <div className="text-sm text-slate-400 py-8 text-center">Connecting to twin feed...</div>
        )}
        <div className="flex items-center gap-4 text-xs text-slate-400 mt-2">
          <span className="flex items-center gap-1"><span className="h-2 w-2 rounded-full bg-emerald-400" />On time (&lt;10m)</span>
          <span className="flex items-center gap-1"><span className="h-2 w-2 rounded-full bg-amber-400" />Minor delay (10-30m)</span>
          <span className="flex items-center gap-1"><span className="h-2 w-2 rounded-full bg-red-400" />Critical (&gt;30m)</span>
          <span className="ml-auto">
            Model: <span className={kpis?.model_active ? "text-emerald-300" : "text-amber-300"}>
              {kpis?.model_active ? kpis.model_name : "fallback (avg-based)"}
            </span>
          </span>
        </div>
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

      <RecommendationList limit={5} />
    </div>
  );
}
