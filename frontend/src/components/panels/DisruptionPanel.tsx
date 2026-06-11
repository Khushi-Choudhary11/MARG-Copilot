import { Zap, CloudFog, AlertTriangle, Radio } from 'lucide-react'

interface Props {
  onInject: (type: string, section_id?: string, label?: string) => void
}

const DISRUPTIONS = [
  {
    type:      'FOG',
    section_id: 's1',
    label:     'Dense Fog · NDLS→GZB',
    icon:      CloudFog,
    color:     'yellow',
    desc:      'Visibility <100m — speed restricted to 30 km/h',
  },
  {
    type:      'TRACK_BLOCK',
    section_id: 's3',
    label:     'Block Track · ALJN→TDL',
    icon:      AlertTriangle,
    color:     'red',
    desc:      'Section S3 blocked — emergency rerouting triggered',
  },
  {
    type:      'SIGNAL_FAIL',
    section_id: 's4',
    label:     'Signal Failure · TDL→ETW',
    icon:      Radio,
    color:     'orange',
    desc:      'Signal at TDL failed — caution order issued',
  },
]

const COLOR_MAP = {
  yellow: 'border-yellow-700 hover:bg-yellow-900/30 text-yellow-300',
  red:    'border-red-700    hover:bg-red-900/30    text-red-300',
  orange: 'border-orange-700 hover:bg-orange-900/30 text-orange-300',
}

export function DisruptionPanel({ onInject }: Props) {
  return (
    <div className="bg-card border border-border rounded-lg p-4 space-y-3">
      <div className="flex items-center gap-2">
        <Zap size={14} className="text-rail" />
        <h3 className="text-xs font-semibold uppercase tracking-widest text-slate-400">
          Disruption Injection
        </h3>
      </div>
      <p className="text-xs text-slate-500">
        Inject a live disruption — MARG responds in real time.
      </p>

      <div className="space-y-2">
        {DISRUPTIONS.map(d => {
          const Icon = d.icon
          const cls  = COLOR_MAP[d.color as keyof typeof COLOR_MAP]
          return (
            <button
              key={d.type + d.section_id}
              onClick={() => onInject(d.type, d.section_id, d.label)}
              className={`w-full text-left p-3 rounded-lg border bg-panel/60
                transition-all duration-150 active:scale-[0.98] ${cls}`}
            >
              <div className="flex items-center gap-2 font-semibold text-sm mb-0.5">
                <Icon size={14} />
                {d.label}
              </div>
              <div className="text-xs text-slate-500">{d.desc}</div>
            </button>
          )
        })}
      </div>
    </div>
  )
}
