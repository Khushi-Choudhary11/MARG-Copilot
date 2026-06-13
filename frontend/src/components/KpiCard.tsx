import { motion } from "framer-motion";

interface Props {
  label: string;
  value: string;
  sublabel?: string;
  accent?: "cyan" | "violet" | "green" | "amber" | "red";
}

const ACCENTS: Record<string, string> = {
  cyan: "from-cyan-400/20 to-cyan-400/0 text-cyan-300",
  violet: "from-violet-400/20 to-violet-400/0 text-violet-300",
  green: "from-emerald-400/20 to-emerald-400/0 text-emerald-300",
  amber: "from-amber-400/20 to-amber-400/0 text-amber-300",
  red: "from-red-400/20 to-red-400/0 text-red-300",
};

export default function KpiCard({ label, value, sublabel, accent = "cyan" }: Props) {
  return (
    <motion.div
      className={`glass rounded-2xl p-4 bg-gradient-to-br ${ACCENTS[accent]} relative overflow-hidden`}
      whileHover={{ scale: 1.02 }}
      transition={{ type: "spring", stiffness: 300, damping: 20 }}
    >
      <div className="text-xs uppercase tracking-wider text-slate-400">{label}</div>
      <div className="text-3xl font-bold mt-1 font-mono">{value}</div>
      {sublabel && <div className="text-xs text-slate-400 mt-1">{sublabel}</div>}
    </motion.div>
  );
}
