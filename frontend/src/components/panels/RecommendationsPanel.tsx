import { CheckCircle, XCircle, ChevronDown, ChevronUp, Brain } from 'lucide-react'
import { useState, useCallback } from 'react'
import { useStore } from '../../store'
import { explApi } from '../../api/endpoints'
import type { Decision } from '../../types'

const TYPE_COLOR: Record<string, string> = {
  HOLD:       'bg-blue-900/60   text-blue-300   border-blue-700',
  REROUTE:    'bg-purple-900/60 text-purple-300 border-purple-700',
  PRECEDENCE: 'bg-orange-900/60 text-orange-300 border-orange-700',
  CROSSING:   'bg-yellow-900/60 text-yellow-300 border-yellow-700',
  OVERTAKING: 'bg-teal-900/60   text-teal-300   border-teal-700',
}

function DecisionCard({ decision, idx }: { decision: Decision; idx: number }) {
  const [expanded, setExpanded]   = useState(false)
  const [explaining, setExplaining] = useState(false)
  const { acceptDecision, overrideDecision, addExplanation, explanations, addToast } = useStore(s => ({
    acceptDecision:  s.acceptDecision,
    overrideDecision: s.overrideDecision,
    addExplanation:  s.addExplanation,
    explanations:    s.explanations,
    addToast:        s.addToast,
  }))

  const key = `${decision.train_id}-${decision.section_id}`
  const explanation = explanations[key]

  const handleExplain = useCallback(async () => {
    if (explanation) { setExpanded(true); return }
    setExplaining(true)
    try {
      const e = await explApi.explain(decision)
      addExplanation(key, e)
      setExpanded(true)
    } catch {
      addToast('error', 'Could not fetch explanation')
    } finally {
      setExplaining(false)
    }
  }, [decision, explanation, key, addExplanation, addToast])

  const typeCls = TYPE_COLOR[decision.decision_type] ?? 'bg-slate-800 text-slate-300 border-slate-600'

  return (
    <div className="bg-panel border border-border rounded-lg overflow-hidden">
      {/* Header */}
      <div className="p-3 space-y-2">
        <div className="flex items-start justify-between gap-2">
          <span className={`text-[10px] font-bold px-2 py-0.5 rounded border ${typeCls}`}>
            {decision.decision_type}
          </span>
          <span className="text-xs text-slate-500 font-mono">{decision.train_id}</span>
        </div>

        <p className="text-sm text-slate-200 leading-snug">{decision.detail}</p>

        <div className="flex gap-3 text-xs text-slate-400">
          <span>💾 <strong className="text-green-400">{decision.delay_saved_min.toFixed(1)} min</strong> saved</span>
          {decision.hold_minutes > 0 &&
            <span>⏱ Hold {decision.hold_minutes} min</span>}
          <span>📊 {(decision.confidence * 100).toFixed(0)}% conf.</span>
        </div>
      </div>

      {/* Explanation */}
      {expanded && explanation && (
        <div className="border-t border-border bg-slate-900/60 p-3">
          <div className="flex items-center gap-1 text-xs text-slate-500 mb-1">
            <Brain size={11} />
            <span className="capitalize">{explanation.source}</span> explanation
            <span className={`ml-auto text-[10px] font-bold px-1.5 py-0.5 rounded ${
              explanation.risk.toLowerCase() === 'low'
                ? 'bg-green-900 text-green-300'
                : 'bg-red-900 text-red-300'
            }`}>
              {explanation.risk.toUpperCase()} RISK
            </span>
          </div>
          <p className="text-xs text-slate-300 leading-relaxed">{explanation.text}</p>
        </div>
      )}

      {/* Actions */}
      <div className="border-t border-border flex">
        <button
          onClick={handleExplain}
          disabled={explaining}
          className="flex-1 py-2 text-xs text-slate-400 hover:bg-slate-800 transition-colors flex items-center justify-center gap-1"
        >
          {explaining ? '...' : expanded ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
          {explaining ? 'Explaining…' : expanded ? 'Hide' : 'Explain'}
        </button>
        <button
          onClick={() => { acceptDecision(idx); addToast('success', `✓ Accepted: ${decision.train_id}`) }}
          className="flex-1 py-2 text-xs text-green-400 hover:bg-green-900/30 transition-colors flex items-center justify-center gap-1 border-x border-border"
        >
          <CheckCircle size={12} /> Accept
        </button>
        <button
          onClick={() => { overrideDecision(idx); addToast('warn', `Override: ${decision.train_id}`) }}
          className="flex-1 py-2 text-xs text-red-400 hover:bg-red-900/30 transition-colors flex items-center justify-center gap-1"
        >
          <XCircle size={12} /> Override
        </button>
      </div>
    </div>
  )
}

export function RecommendationsPanel() {
  const decisions = useStore(s => s.decisions)

  return (
    <div className="bg-card border border-border rounded-lg p-4 flex flex-col gap-3 min-h-0">
      <div className="flex items-center justify-between shrink-0">
        <h3 className="text-xs font-semibold uppercase tracking-widest text-slate-400">
          Recommendations
        </h3>
        {decisions.length > 0 &&
          <span className="text-xs bg-rail/20 text-rail border border-rail/40 rounded-full px-2 py-0.5">
            {decisions.length}
          </span>}
      </div>

      {decisions.length === 0 ? (
        <div className="flex-1 flex items-center justify-center">
          <p className="text-xs text-slate-600 text-center">
            No active recommendations.<br />
            Optimizer runs every 30 s.
          </p>
        </div>
      ) : (
        <div className="space-y-2 overflow-y-auto pr-1 flex-1">
          {decisions.map((d, i) => (
            <DecisionCard key={`${d.train_id}-${d.section_id}-${i}`} decision={d} idx={i} />
          ))}
        </div>
      )}
    </div>
  )
}
