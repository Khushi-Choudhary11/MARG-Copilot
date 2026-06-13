import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { api, type TrainDetail as TrainDetailType } from "../api";
import { motion } from "framer-motion";

const STATUS_STYLE: Record<string, string> = {
  done: "bg-slate-500",
  current: "bg-cyan-400 pulse-dot",
  upcoming: "bg-slate-700",
};

function delayColor(delay: number | null | undefined) {
  if (delay == null) return "text-slate-400";
  if (delay >= 30) return "text-red-400";
  if (delay >= 10) return "text-amber-400";
  return "text-emerald-400";
}

export default function TrainDetail() {
  const { trainNumber } = useParams();
  const { data, isLoading, error } = useQuery<TrainDetailType>({
    queryKey: ["train", trainNumber],
    queryFn: async () => (await api.get(`/api/trains/${trainNumber}`)).data,
    refetchInterval: 5000,
  });

  if (isLoading) return <div className="text-sm text-slate-400">Loading...</div>;
  if (error || !data)
    return (
      <div className="text-sm text-slate-400">
        Train not found for the demo date.{" "}
        <Link to="/trains" className="text-cyan-300 hover:underline">
          Back to trains
        </Link>
      </div>
    );

  return (
    <div className="flex flex-col gap-5">
      <div>
        <Link to="/trains" className="text-xs text-slate-400 hover:text-cyan-300">
          ← Back to trains
        </Link>
        <h1 className="text-2xl font-bold text-gradient mt-1">
          {data.train_number} · {data.train_name}
        </h1>
        <p className="text-sm text-slate-400">
          {data.train_type} · Priority P{data.priority} · {data.corridor_direction} ·{" "}
          {data.total_distance_km ? `${data.total_distance_km.toFixed(0)} km` : ""}
        </p>
        <p className="text-xs text-slate-500">
          {data.source_station_code} → {data.destination_station_code} · Operates: {data.operating_days}
        </p>
      </div>

      <div className="glass rounded-2xl p-4">
        <h2 className="font-semibold text-slate-200 mb-4">Corridor Route Timeline</h2>
        <div className="flex flex-col gap-0">
          {data.route_stops.map((stop, i) => (
            <motion.div
              key={stop.station_code}
              initial={{ opacity: 0, x: -8 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: i * 0.05 }}
              className="flex items-center gap-4 py-3 border-l-2 border-white/10 pl-4 relative"
            >
              <span
                className={`absolute -left-[7px] h-3 w-3 rounded-full ${STATUS_STYLE[stop.status]}`}
              />
              <div className="w-16 font-mono font-bold">{stop.station_code}</div>
              <div className="text-xs text-slate-400 w-32">
                Sched arr: {stop.scheduled_arrival ? new Date(stop.scheduled_arrival).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" }) : "–"}
              </div>
              <div className="text-xs text-slate-400 w-32">
                Sched dep: {stop.scheduled_departure ? new Date(stop.scheduled_departure).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" }) : "–"}
              </div>
              <div className={`text-sm font-mono ${delayColor(stop.current_delay)}`}>
                current: {stop.current_delay.toFixed(0)}m
              </div>
              <div className={`text-sm font-mono ${delayColor(stop.predicted_delay_next)}`}>
                predicted next: {stop.predicted_delay_next?.toFixed(0) ?? "–"}m
                <span className="text-[10px] text-slate-500 ml-1">({stop.prediction_source})</span>
              </div>
              <div className="ml-auto text-xs uppercase tracking-wide text-slate-500">{stop.status}</div>
            </motion.div>
          ))}
        </div>
      </div>
    </div>
  );
}
