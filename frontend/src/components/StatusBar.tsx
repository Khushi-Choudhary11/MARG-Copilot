import { Activity, Wifi, WifiOff, Play, Pause, Square } from 'lucide-react'
import { useStore } from '../store'

interface Props {
  onStop:   () => void
  onPause:  () => void
  onResume: () => void
}

export function StatusBar({ onStop, onPause, onResume }: Props) {
  const tick      = useStore(s => s.tick)
  const connected = useStore(s => s.connected)
  const status    = useStore(s => s.status)
  const simStatus = status?.status ?? 'stopped'

  return (
    <header className="h-14 bg-card border-b border-border flex items-center px-4 gap-4 shrink-0">
      {/* Brand */}
      <div className="flex items-center gap-2 mr-2">
        <span className="text-rail text-xl font-black tracking-tight">MARG</span>
        <span className="text-slate-500 text-xs hidden sm:block">Control Tower</span>
      </div>

      {/* Connection pill */}
      <div className={`flex items-center gap-1 text-xs px-2 py-0.5 rounded-full border ${
        connected
          ? 'border-green-700 text-green-400 bg-green-900/20'
          : 'border-red-800  text-red-400  bg-red-900/20'
      }`}>
        {connected ? <Wifi size={12} /> : <WifiOff size={12} />}
        {connected ? 'Live' : 'Offline'}
      </div>

      {/* Tick */}
      <div className="flex items-center gap-1 text-xs text-slate-400 font-mono">
        <Activity size={12} className="text-rail" />
        T+{tick}
      </div>

      {/* Corridor label */}
      <div className="hidden md:flex items-center gap-1 text-xs text-slate-500">
        <span>NDLS</span>
        <span className="text-rail">────────</span>
        <span>CNB</span>
        <span className="ml-1 text-slate-600">(440 km · 6 stations)</span>
      </div>

      <div className="flex-1" />

      {/* Sim status badge */}
      <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${
        simStatus === 'running' ? 'bg-green-900/40 text-green-400' :
        simStatus === 'paused'  ? 'bg-yellow-900/40 text-yellow-400' :
                                   'bg-slate-800 text-slate-400'
      }`}>
        {simStatus.toUpperCase()}
      </span>

      {/* Controls */}
      <div className="flex gap-1">
        <button
          onClick={onResume}
          className="p-1.5 rounded hover:bg-green-900/40 text-green-400 transition-colors"
          title="Resume"
        >
          <Play size={16} />
        </button>
        <button
          onClick={onPause}
          className="p-1.5 rounded hover:bg-yellow-900/40 text-yellow-400 transition-colors"
          title="Pause"
        >
          <Pause size={16} />
        </button>
        <button
          onClick={onStop}
          className="p-1.5 rounded hover:bg-red-900/40 text-red-400 transition-colors"
          title="Stop"
        >
          <Square size={16} />
        </button>
      </div>
    </header>
  )
}
