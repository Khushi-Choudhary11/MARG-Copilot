import { motion } from "framer-motion";
import { Link } from "react-router-dom";
import type { LiveTrainPosition, StationOut } from "../api";
import { trainIcon } from "../utils/trainIcons";

interface Props {
  station: StationOut;
  trains: LiveTrainPosition[];
  onClose: () => void;
}

export default function StationInfoCard({ station, trains, onClose }: Props) {
  const related = trains.filter(
    (t) => t.from_station === station.station_code || t.to_station === station.station_code
  );

  return (
    <motion.div
      initial={{ opacity: 0, height: 0 }}
      animate={{ opacity: 1, height: "auto" }}
      exit={{ opacity: 0, height: 0 }}
      className="glass rounded-2xl p-4 mt-3 overflow-hidden"
    >
      <div className="flex items-start justify-between">
        <div>
          <div className="text-lg font-bold text-cyan-300">{station.station_name}</div>
          <div className="text-xs text-slate-400 font-mono">{station.station_code}</div>
        </div>
        <button onClick={onClose} className="text-slate-400 hover:text-slate-200 text-sm">
          ✕
        </button>
      </div>

      <div className="grid grid-cols-3 gap-3 mt-3 text-sm">
        <div>
          <div className="text-xs text-slate-500 uppercase">Platforms</div>
          <div className="font-mono font-semibold">{station.platforms ?? "–"}</div>
        </div>
        <div>
          <div className="text-xs text-slate-500 uppercase">Main Tracks</div>
          <div className="font-mono font-semibold">{station.main_tracks ?? "–"}</div>
        </div>
        <div>
          <div className="text-xs text-slate-500 uppercase">Loop Lines</div>
          <div className="font-mono font-semibold">{station.loop_lines ?? "–"}</div>
        </div>
        <div className="col-span-3">
          <div className="text-xs text-slate-500 uppercase">Category</div>
          <div className="font-mono font-semibold">{station.station_category ?? "–"}</div>
        </div>
      </div>

      <div className="mt-4">
        <div className="text-xs text-slate-500 uppercase mb-2">Trains at / approaching this station</div>
        {related.length === 0 && <div className="text-sm text-slate-400">No trains currently in this section.</div>}
        <div className="flex flex-col gap-1">
          {related.map((t) => (
            <Link
              key={t.train_number}
              to={`/trains/${t.train_number}`}
              className="flex items-center gap-2 text-sm rounded-lg px-2 py-1 hover:bg-white/5"
            >
              <span>{trainIcon(t.train_type)}</span>
              <span className="font-mono font-semibold">{t.train_number}</span>
              <span className="text-slate-400 text-xs truncate">{t.train_name}</span>
              <span className="ml-auto text-xs text-slate-500">
                {t.from_station} → {t.to_station} ({Math.round(t.progress * 100)}%)
              </span>
            </Link>
          ))}
        </div>
      </div>
    </motion.div>
  );
}
