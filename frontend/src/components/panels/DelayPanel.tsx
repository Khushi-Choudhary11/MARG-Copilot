import { TrendingUp, Train } from 'lucide-react'
import { useStore } from '../../store'
import { riskBadge } from '../map/CongestionLayer'

export function DelayPanel() {
  const trains     = useStore(s => s.trains)
  const congestion = useStore(s => s.congestion)

  const congestionMap = Object.fromEntries(
    congestion.map(c => [c.section_id, c])
  )

  return (
    <div className="bg-card border border-border rounded-lg p-4 space-y-3">
      {/* Section congestion */}
      <div>
        <div className="flex items-center gap-2 mb-2">
          <TrendingUp size={13} className="text-rail" />
          <h3 className="text-xs font-semibold uppercase tracking-widest text-slate-400">
            Section Congestion
          </h3>
        </div>
        <div className="space-y-1">
          {congestion.length === 0 ? (
            <p className="text-xs text-slate-600">Loading…</p>
          ) : congestion.map(c => {
            const pct = (c.congestion_score_h1 * 100).toFixed(0)
            const { text, cls } = riskBadge(c.risk_level)
            const barColor =
              c.risk_level === 'high'   ? 'bg-red-500' :
              c.risk_level === 'medium' ? 'bg-yellow-500' : 'bg-green-500'
            return (
              <div key={c.section_id} className="flex items-center gap-2 text-xs">
                <span className="font-mono text-slate-400 w-6">{c.section_id.toUpperCase()}</span>
                <div className="flex-1 h-1.5 bg-slate-700 rounded-full overflow-hidden">
                  <div
                    className={`h-full ${barColor} transition-all duration-700`}
                    style={{ width: `${pct}%` }}
                  />
                </div>
                <span className="text-slate-400 w-8 text-right">{pct}%</span>
                <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${cls}`}>{text}</span>
              </div>
            )
          })}
        </div>
      </div>

      {/* Live trains */}
      <div>
        <div className="flex items-center gap-2 mb-2">
          <Train size={13} className="text-rail" />
          <h3 className="text-xs font-semibold uppercase tracking-widest text-slate-400">
            Train Delays
          </h3>
        </div>
        <div className="space-y-1 max-h-40 overflow-y-auto">
          {trains.length === 0 ? (
            <p className="text-xs text-slate-600">Waiting for simulation…</p>
          ) : [...trains]
            .sort((a, b) => b.delay_min - a.delay_min)
            .map(t => {
              const d = t.delay_min
              const cls = d > 15 ? 'text-red-400' : d > 5 ? 'text-yellow-400' : 'text-green-400'
              const sec = congestionMap[t.section_id]
              return (
                <div key={t.train_id} className="flex items-center gap-2 text-xs py-0.5">
                  <span className="font-mono text-slate-400 w-12">{t.train_id}</span>
                  <span className="text-slate-500 capitalize text-[10px] w-16">{t.category}</span>
                  <span className={`font-bold ${cls} ml-auto`}>
                    {d > 0 ? `+${d.toFixed(0)}m` : 'ON TIME'}
                  </span>
                  {sec && (
                    <span className={`text-[10px] px-1 rounded ${riskBadge(sec.risk_level).cls}`}>
                      {t.section_id.toUpperCase()}
                    </span>
                  )}
                </div>
              )
            })}
        </div>
      </div>
    </div>
  )
}
