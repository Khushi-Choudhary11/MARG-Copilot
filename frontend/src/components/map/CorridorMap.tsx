import { MapContainer, TileLayer, Polyline, CircleMarker, Tooltip } from 'react-leaflet'
import 'leaflet/dist/leaflet.css'
import { useStore } from '../../store'
import { STATIONS, SECTIONS, STATION_BY_CODE, sectionMidpoint, CORRIDOR_BOUNDS } from '../../data/corridor'
import { TrainMarker } from './TrainMarker'
import { congestionColor } from './CongestionLayer'

export function CorridorMap() {
  const trains     = useStore(s => s.trains)
  const congestion = useStore(s => s.congestion)

  const congestionMap = Object.fromEntries(
    congestion.map(c => [c.section_id, c.congestion_score_h1])
  )

  return (
    <MapContainer
      bounds={CORRIDOR_BOUNDS}
      className="w-full h-full rounded-lg"
      zoomControl={true}
      attributionControl={false}
    >
      {/* Dark basemap */}
      <TileLayer
        url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
        attribution="&copy; CartoDB"
      />

      {/* Section polylines — colored by congestion */}
      {SECTIONS.map(sec => {
        const a = STATION_BY_CODE[sec.from]?.latlng
        const b = STATION_BY_CODE[sec.to]?.latlng
        if (!a || !b) return null
        const score = congestionMap[sec.id] ?? 0
        const color = congestionColor(score)
        return (
          <Polyline
            key={sec.id}
            positions={[a, b]}
            pathOptions={{
              color,
              weight:    sec.is_single_line ? 3 : 5,
              opacity:   0.85,
              dashArray: sec.is_single_line ? '8 4' : undefined,
            }}
          >
            <Tooltip sticky>
              <span className="text-xs font-mono">
                {sec.id.toUpperCase()} · {sec.from}→{sec.to}
                {sec.is_single_line && ' (single line)'}
                <br />congestion: {(score * 100).toFixed(0)}%
              </span>
            </Tooltip>
          </Polyline>
        )
      })}

      {/* Station markers */}
      {STATIONS.map(st => (
        <CircleMarker
          key={st.id}
          center={st.latlng}
          radius={6}
          pathOptions={{ color: '#f97316', fillColor: '#1e293b', fillOpacity: 1, weight: 2 }}
        >
          <Tooltip permanent direction="top" offset={[0, -8]}>
            <span className="text-xs font-bold">{st.code}</span>
          </Tooltip>
        </CircleMarker>
      ))}

      {/* Animated train markers */}
      {trains.map(train => {
        const pos = sectionMidpoint(train.section_id)
        return <TrainMarker key={train.train_id} train={train} position={pos} />
      })}
    </MapContainer>
  )
}
