import { useEffect } from 'react'
import { CorridorMap }          from './components/map/CorridorMap'
import { StatusBar }            from './components/StatusBar'
import { DisruptionPanel }      from './components/panels/DisruptionPanel'
import { RecommendationsPanel } from './components/panels/RecommendationsPanel'
import { DelayPanel }           from './components/panels/DelayPanel'
import { ImpactCounter }        from './components/ImpactCounter'
import { ToastContainer }       from './components/panels/ToastContainer'
import { useSimulationWs }      from './hooks/useWebSocket'
import { useSimulationControls } from './hooks/useSimulationControls'

export default function App() {
  // Start WS feed and periodic polling
  useSimulationWs()
  const { handleStop, handlePause, handleResume, injectDisruption } =
    useSimulationControls()

  return (
    <div className="h-screen w-screen flex flex-col bg-panel text-slate-100 overflow-hidden">
      {/* Top bar */}
      <StatusBar
        onStop={handleStop}
        onPause={handlePause}
        onResume={handleResume}
      />

      {/* Main content — three-column layout */}
      <div className="flex-1 flex gap-0 min-h-0">

        {/* ── Left sidebar ─────────────────────────────────────────────── */}
        <aside className="w-72 shrink-0 flex flex-col gap-3 p-3 overflow-y-auto
                          border-r border-border bg-panel/80">
          <DisruptionPanel onInject={injectDisruption} />
          <DelayPanel />
        </aside>

        {/* ── Map (center) ─────────────────────────────────────────────── */}
        <main className="flex-1 relative">
          <CorridorMap />

          {/* Overlay: legend */}
          <div className="absolute bottom-4 left-4 z-[1000]
                          bg-card/90 border border-border rounded-lg p-2 text-xs space-y-1
                          backdrop-blur-sm">
            <div className="font-semibold text-slate-400 mb-1">Congestion</div>
            {[
              { color: '#22c55e', label: 'Low  (<35%)' },
              { color: '#eab308', label: 'Med  (35–65%)' },
              { color: '#f97316', label: 'High (65–85%)' },
              { color: '#ef4444', label: 'Crit (>85%)' },
            ].map(r => (
              <div key={r.label} className="flex items-center gap-2">
                <div className="w-6 h-1.5 rounded-full" style={{ background: r.color }} />
                <span className="text-slate-400">{r.label}</span>
              </div>
            ))}
            <div className="border-t border-border mt-1 pt-1 text-slate-500">
              <span className="font-mono">- -</span> single-line section
            </div>
          </div>
        </main>

        {/* ── Right sidebar ─────────────────────────────────────────────── */}
        <aside className="w-80 shrink-0 flex flex-col gap-3 p-3 overflow-y-auto
                          border-l border-border bg-panel/80">
          <ImpactCounter />
          <RecommendationsPanel />
        </aside>
      </div>

      {/* Floating toasts */}
      <ToastContainer />
    </div>
  )
}
