import { Marker, Tooltip } from 'react-leaflet'
import L from 'leaflet'
import type { TrainPosition } from '../../types'

const CATEGORY_COLOR: Record<string, string> = {
  superfast: '#f97316',
  mail:      '#a855f7',
  express:   '#3b82f6',
  goods:     '#6b7280',
}

function trainIcon(train: TrainPosition): L.DivIcon {
  const color = CATEGORY_COLOR[train.category] ?? '#3b82f6'
  const delay = train.delay_min
  const ring  = delay > 15 ? '#ef4444' : delay > 5 ? '#eab308' : '#22c55e'
  const arrow = train.direction === 'DOWN' ? '→' : '←'

  const html = `
    <div style="
      background:${color};border:2px solid ${ring};
      border-radius:50%;width:28px;height:28px;
      display:flex;align-items:center;justify-content:center;
      font-size:12px;font-weight:700;color:#fff;
      box-shadow:0 0 6px ${ring}88;
      cursor:pointer;
    " title="${train.train_id}">
      ${arrow}
    </div>`

  return L.divIcon({ html, className: '', iconSize: [28, 28], iconAnchor: [14, 14] })
}

interface Props {
  train:    TrainPosition
  position: [number, number]
}

export function TrainMarker({ train, position }: Props) {
  return (
    <Marker position={position} icon={trainIcon(train)}>
      <Tooltip>
        <div className="text-xs space-y-0.5">
          <div className="font-bold">🚂 {train.train_id}</div>
          <div>Category: <span className="capitalize">{train.category}</span></div>
          <div>Section:  {train.section_id.toUpperCase()}</div>
          <div>Delay:    <span className={train.delay_min > 5 ? 'text-red-400' : 'text-green-400'}>
            {train.delay_min.toFixed(1)} min
          </span></div>
          <div>Speed:    {train.speed_kmh} km/h</div>
          <div>Dir:      {train.direction}</div>
        </div>
      </Tooltip>
    </Marker>
  )
}
