/** Map a 0-1 congestion score to a hex color (green → yellow → red). */
export function congestionColor(score: number): string {
  if (score < 0.35) return '#22c55e'   // green  — low
  if (score < 0.65) return '#eab308'   // yellow — medium
  if (score < 0.85) return '#f97316'   // orange — high
  return '#ef4444'                      // red    — critical
}

export function riskBadge(level: string): { text: string; cls: string } {
  switch (level) {
    case 'low':    return { text: 'LOW',    cls: 'bg-green-900  text-green-300'  }
    case 'medium': return { text: 'MED',    cls: 'bg-yellow-900 text-yellow-300' }
    case 'high':   return { text: 'HIGH',   cls: 'bg-red-900    text-red-300'    }
    default:       return { text: level.toUpperCase(), cls: 'bg-slate-700 text-slate-300' }
  }
}
