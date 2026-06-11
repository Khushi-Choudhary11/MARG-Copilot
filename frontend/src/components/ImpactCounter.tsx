import { useStore } from '../store'

export function ImpactCounter() {
  const delaySaved    = useStore(s => s.delaySaved)
  const baselineDelay = useStore(s => s.baselineDelay)
  const pct = baselineDelay > 0
    ? Math.min(100, (delaySaved / baselineDelay) * 100)
    : 0

  return (
    <div className="bg-card border border-border rounded-lg p-4 space-y-3">
      <h3 className="text-xs font-semibold uppercase tracking-widest text-slate-400">
        Impact Counter
      </h3>

      <div className="text-center">
        <span className="text-4xl font-black text-rail tabular-nums animate-count-up">
          {Math.round(delaySaved)}
        </span>
        <span className="ml-1 text-sm text-slate-400">min saved</span>
      </div>

      {/* Progress bar vs baseline */}
      <div>
        <div className="flex justify-between text-xs text-slate-500 mb-1">
          <span>vs. no-intervention baseline</span>
          <span className="text-green-400 font-semibold">{pct.toFixed(0)}%</span>
        </div>
        <div className="h-2 bg-slate-700 rounded-full overflow-hidden">
          <div
            className="h-full bg-gradient-to-r from-green-500 to-emerald-400 transition-all duration-700"
            style={{ width: `${pct}%` }}
          />
        </div>
      </div>

      <div className="grid grid-cols-2 gap-2 text-center text-xs">
        <div className="bg-panel rounded p-2">
          <div className="text-slate-400">Baseline</div>
          <div className="font-bold text-slate-300">{Math.round(baselineDelay)} min</div>
        </div>
        <div className="bg-panel rounded p-2">
          <div className="text-slate-400">Optimized</div>
          <div className="font-bold text-green-400">
            {Math.round(Math.max(0, baselineDelay - delaySaved))} min
          </div>
        </div>
      </div>
    </div>
  )
}
