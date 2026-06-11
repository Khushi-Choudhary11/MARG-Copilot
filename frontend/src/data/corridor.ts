import type { Station, Section } from '../types'

// NDLS → CNB corridor — real geographic coordinates
export const STATIONS: Station[] = [
  { id: 'ndls', code: 'NDLS', name: 'New Delhi',  latlng: [28.6448,  77.2167] },
  { id: 'gzb',  code: 'GZB',  name: 'Ghaziabad',  latlng: [28.6692,  77.4538] },
  { id: 'aljn', code: 'ALJN', name: 'Aligarh Jn', latlng: [27.8847,  78.0776] },
  { id: 'tdl',  code: 'TDL',  name: 'Tundla Jn',  latlng: [27.1893,  78.9164] },
  { id: 'etw',  code: 'ETW',  name: 'Etawah',      latlng: [26.7838,  79.0200] },
  { id: 'cnb',  code: 'CNB',  name: 'Kanpur',      latlng: [26.4499,  80.3319] },
]

export const SECTIONS: Section[] = [
  { id: 's1', from: 'NDLS', to: 'GZB',  is_single_line: false },
  { id: 's2', from: 'GZB',  to: 'ALJN', is_single_line: true  },
  { id: 's3', from: 'ALJN', to: 'TDL',  is_single_line: true  },
  { id: 's4', from: 'TDL',  to: 'ETW',  is_single_line: false },
  { id: 's5', from: 'ETW',  to: 'CNB',  is_single_line: false },
]

export const STATION_BY_CODE = Object.fromEntries(
  STATIONS.map(s => [s.code, s])
)

/** Midpoint lat/lng of a section (for placing train markers). */
export function sectionMidpoint(sectionId: string): [number, number] {
  const sec = SECTIONS.find(s => s.id === sectionId)
  if (!sec) return [27.5, 78.5]
  const a = STATION_BY_CODE[sec.from]?.latlng ?? [27.5, 78.5]
  const b = STATION_BY_CODE[sec.to]?.latlng   ?? [27.5, 78.5]
  return [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2]
}

/** Polyline of the full corridor */
export const CORRIDOR_POLYLINE: [number, number][] =
  STATIONS.map(s => s.latlng)

/** Map bounds that fit the corridor with padding */
export const CORRIDOR_BOUNDS: [[number, number], [number, number]] = [
  [26.0, 76.8],
  [29.0, 80.8],
]
