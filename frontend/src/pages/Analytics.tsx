import { useQuery } from "@tanstack/react-query";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api, type StationDelayStat, type TrainTypeDelay, type KpiSummary } from "../api";
import KpiCard from "../components/KpiCard";

export default function Analytics() {
  const { data: stationDelays } = useQuery<StationDelayStat[]>({
    queryKey: ["station-delays"],
    queryFn: async () => (await api.get("/api/analytics/station-delays")).data,
    refetchInterval: 30000,
  });

  const { data: trainTypeDelays } = useQuery<TrainTypeDelay[]>({
    queryKey: ["train-type-delays"],
    queryFn: async () => (await api.get("/api/analytics/train-type-delays")).data,
    refetchInterval: 30000,
  });

  const { data: kpis } = useQuery<KpiSummary>({
    queryKey: ["kpis"],
    queryFn: async () => (await api.get("/api/analytics/kpis")).data,
    refetchInterval: 5000,
  });

  return (
    <div className="flex flex-col gap-5">
      <div>
        <h1 className="text-2xl font-bold text-gradient">Analytics</h1>
        <p className="text-sm text-slate-400">
          Demo-day ({kpis?.demo_date ?? "—"}) delay patterns across the corridor.
        </p>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <KpiCard label="Model in use" value={kpis?.model_active ? kpis.model_name : "Fallback"} accent={kpis?.model_active ? "green" : "amber"} />
        <KpiCard label="Avg current delay" value={`${kpis?.avg_current_delay?.toFixed(1) ?? "–"} min`} accent="cyan" />
        <KpiCard label="Avg predicted delay" value={`${kpis?.avg_predicted_delay?.toFixed(1) ?? "–"} min`} accent="violet" />
        <KpiCard label="On-time %" value={`${kpis?.on_time_pct?.toFixed(0) ?? "–"}%`} accent="green" />
      </div>

      <div className="glass rounded-2xl p-4">
        <h2 className="font-semibold text-slate-200 mb-3">Average Delay by Station (Demo Day)</h2>
        <ResponsiveContainer width="100%" height={300}>
          <BarChart data={stationDelays ?? []}>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(148,163,184,0.1)" />
            <XAxis dataKey="station_code" stroke="#94a3b8" />
            <YAxis stroke="#94a3b8" unit="m" />
            <Tooltip
              contentStyle={{ background: "#11172a", border: "1px solid rgba(148,163,184,0.2)", borderRadius: 8 }}
            />
            <Legend />
            <Bar dataKey="avg_current_delay" name="Avg current delay (demo day)" fill="#22d3ee" radius={[4, 4, 0, 0]} />
            <Bar dataKey="avg_station_historical_delay" name="Historical avg delay" fill="#a78bfa" radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>

      <div className="glass rounded-2xl p-4">
        <h2 className="font-semibold text-slate-200 mb-3">Average Delay by Train Type</h2>
        <ResponsiveContainer width="100%" height={300}>
          <BarChart data={trainTypeDelays ?? []} layout="vertical" margin={{ left: 40 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(148,163,184,0.1)" />
            <XAxis type="number" stroke="#94a3b8" unit="m" />
            <YAxis dataKey="train_type" type="category" stroke="#94a3b8" width={120} />
            <Tooltip
              contentStyle={{ background: "#11172a", border: "1px solid rgba(148,163,184,0.2)", borderRadius: 8 }}
            />
            <Bar dataKey="avg_delay" name="Avg delay" fill="#34d399" radius={[0, 4, 4, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
