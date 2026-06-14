import { motion, AnimatePresence } from "framer-motion";
import type { LiveTrainPosition, StationOut } from "../api";
import { trainIcon } from "../utils/trainIcons";

const CORRIDOR_ORDER = ["NDLS", "GZB", "ALJN", "TDL", "ETW", "CNB"];

function delayColor(delay: number | null | undefined) {
  if (delay == null) return "#64748b";
  if (delay >= 30) return "#f87171";
  if (delay >= 10) return "#fbbf24";
  return "#34d399";
}

interface Props {
  stations: StationOut[];
  trains: LiveTrainPosition[];
  compact?: boolean;
  onSelectTrain?: (trainNumber: string) => void;
  onSelectStation?: (stationCode: string) => void;
  selectedStation?: string | null;
}

export default function CorridorSchematic({
  stations,
  trains,
  compact,
  onSelectTrain,
  onSelectStation,
  selectedStation,
}: Props) {
  const width = 1000;
  const height = compact ? 180 : 320;
  const trackY = height / 2;
  const margin = 60;
  const usable = width - margin * 2;

  const orderedStations = CORRIDOR_ORDER.map((code) =>
    stations.find((s) => s.station_code === code)
  ).filter((s): s is StationOut => !!s);

  const xFor = (code: string) => {
    const idx = CORRIDOR_ORDER.indexOf(code);
    if (idx === -1) return margin;
    return margin + (usable * idx) / (CORRIDOR_ORDER.length - 1);
  };

  const running = trains.filter((t) => t.status === "running");
  const scheduled = trains.filter((t) => t.status === "scheduled");
  const completed = trains.filter((t) => t.status === "completed");

  // Group same-station "waiting"/"arrived" trains so we can show a handful of
  // icons plus a "+N" badge instead of one icon per train (which could be 60+).
  const MAX_STACK = 4;
  const groupByStation = (list: typeof trains) => {
    const groups = new Map<string, typeof trains>();
    for (const t of list) {
      const station = (list === scheduled ? t.to_station : t.from_station) ?? CORRIDOR_ORDER[0];
      const isDown = t.corridor_direction?.startsWith("DOWN");
      const key = `${station}-${isDown ? "down" : "up"}`;
      const arr = groups.get(key) ?? [];
      arr.push(t);
      groups.set(key, arr);
    }
    return groups;
  };

  return (
    <div className="w-full overflow-x-auto">
      <svg viewBox={`0 0 ${width} ${height}`} className="w-full min-w-[640px]" style={{ height }}>
        {/* DOWN track (NDLS->CNB), slightly above center */}
        <line
          x1={margin}
          y1={trackY - 8}
          x2={width - margin}
          y2={trackY - 8}
          stroke="#22d3ee"
          strokeOpacity={0.35}
          strokeWidth={3}
        />
        {/* UP track (CNB->NDLS), slightly below center */}
        <line
          x1={margin}
          y1={trackY + 8}
          x2={width - margin}
          y2={trackY + 8}
          stroke="#a78bfa"
          strokeOpacity={0.35}
          strokeWidth={3}
        />

        {/* Station markers */}
        {orderedStations.map((s) => {
          const x = xFor(s.station_code);
          const isSelected = selectedStation === s.station_code;
          return (
            <g
              key={s.station_code}
              onClick={() => onSelectStation?.(s.station_code)}
              style={{ cursor: onSelectStation ? "pointer" : "default" }}
            >
              <line x1={x} y1={trackY - 22} x2={x} y2={trackY + 22} stroke="#334155" strokeWidth={1} />
              <circle
                cx={x}
                cy={trackY}
                r={isSelected ? 7 : 5}
                fill={isSelected ? "#22d3ee" : "#0a0e17"}
                stroke="#94a3b8"
                strokeWidth={1.5}
              />
              <text
                x={x}
                y={compact ? trackY - 30 : trackY - 32}
                textAnchor="middle"
                fontSize={13}
                fontWeight={600}
                fill={isSelected ? "#22d3ee" : "#cbd5e1"}
              >
                {s.station_code}
              </text>
              {!compact && (
                <text x={x} y={trackY + 38} textAnchor="middle" fontSize={10} fill="#64748b">
                  PF {s.platforms ?? "-"}
                </text>
              )}
            </g>
          );
        })}

        {/* Trains */}
        <AnimatePresence>
          {running.map((t) => {
            const xa = xFor(t.from_station ?? CORRIDOR_ORDER[0]);
            const xb = xFor(t.to_station ?? CORRIDOR_ORDER[0]);
            const x = xa + (xb - xa) * t.progress;
            const isDown = t.corridor_direction?.startsWith("DOWN");
            const y = isDown ? trackY - 8 : trackY + 8;
            const color = delayColor(t.predicted_delay_next ?? t.current_delay);
            return (
              <motion.g
                key={t.train_number}
                initial={false}
                animate={{ x, y }}
                transition={{ duration: 2.5, ease: "linear" }}
                onClick={() => onSelectTrain?.(t.train_number)}
                style={{ cursor: onSelectTrain ? "pointer" : "default" }}
              >
                <circle r={11} fill={color} fillOpacity={0.18} />
                <circle r={9} fill="#0a0e17" stroke={color} strokeWidth={2} />
                <text textAnchor="middle" dominantBaseline="central" fontSize={11}>
                  {trainIcon(t.train_type)}
                  <title>
                    {t.train_number} {t.train_name} — {t.current_delay.toFixed(0)}m delay
                  </title>
                </text>
                {!compact && (
                  <text y={-14} textAnchor="middle" fontSize={10} fill="#e2e8f0" fontFamily="var(--font-mono)">
                    {t.train_number}
                  </text>
                )}
              </motion.g>
            );
          })}
        </AnimatePresence>

        {/* Trains waiting to depart (scheduled) and trains that finished today (completed) —
            shown dimmed near their origin/destination station so the corridor looks fully populated.
            Each station/direction group shows up to MAX_STACK icons plus a "+N" badge. */}
        {[...groupByStation(scheduled).entries()].map(([key, group]) => {
          const [station, dir] = key.split("-");
          const x = xFor(station);
          const isDown = dir === "down";
          const sign = isDown ? -1 : 1;
          const y = trackY + sign * 8 + sign * 16;
          const shown = group.slice(0, MAX_STACK);
          const extra = group.length - shown.length;
          return (
            <g key={`sched-${key}`}>
              {shown.map((t, i) => (
                <g
                  key={t.train_number}
                  transform={`translate(${x + (i - (shown.length - 1) / 2) * 14}, ${y})`}
                  onClick={() => onSelectTrain?.(t.train_number)}
                  style={{ cursor: onSelectTrain ? "pointer" : "default" }}
                  opacity={0.45}
                >
                  <circle r={7} fill="#0a0e17" stroke="#64748b" strokeWidth={1.5} strokeDasharray="2,2" />
                  <text textAnchor="middle" dominantBaseline="central" fontSize={9}>
                    {trainIcon(t.train_type)}
                    <title>
                      {t.train_number} {t.train_name} — waiting to depart {station}
                    </title>
                  </text>
                </g>
              ))}
              {extra > 0 && (
                <text
                  x={x + (shown.length - (shown.length - 1) / 2) * 14 + 4}
                  y={y}
                  textAnchor="start"
                  dominantBaseline="central"
                  fontSize={10}
                  fill="#64748b"
                >
                  +{extra}
                </text>
              )}
            </g>
          );
        })}
        {[...groupByStation(completed).entries()].map(([key, group]) => {
          const [station, dir] = key.split("-");
          const x = xFor(station);
          const isDown = dir === "down";
          const sign = isDown ? -1 : 1;
          const y = trackY + sign * 8 + sign * 32;
          const shown = group.slice(0, MAX_STACK);
          const extra = group.length - shown.length;
          return (
            <g key={`done-${key}`}>
              {shown.map((t, i) => (
                <g
                  key={t.train_number}
                  transform={`translate(${x + (i - (shown.length - 1) / 2) * 14}, ${y})`}
                  onClick={() => onSelectTrain?.(t.train_number)}
                  style={{ cursor: onSelectTrain ? "pointer" : "default" }}
                  opacity={0.3}
                >
                  <circle r={7} fill="#0a0e17" stroke="#475569" strokeWidth={1.5} />
                  <text textAnchor="middle" dominantBaseline="central" fontSize={9}>
                    {trainIcon(t.train_type)}
                    <title>
                      {t.train_number} {t.train_name} — arrived at {station} ({t.current_delay.toFixed(0)}m delay)
                    </title>
                  </text>
                </g>
              ))}
              {extra > 0 && (
                <text
                  x={x + (shown.length - (shown.length - 1) / 2) * 14 + 4}
                  y={y}
                  textAnchor="start"
                  dominantBaseline="central"
                  fontSize={10}
                  fill="#64748b"
                >
                  +{extra}
                </text>
              )}
            </g>
          );
        })}
      </svg>
    </div>
  );
}
