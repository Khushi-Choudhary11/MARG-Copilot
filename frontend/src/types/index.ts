// ── Simulation ───────────────────────────────────────────────────────────────

export interface TrainPosition {
  train_id:   string
  category:   'superfast' | 'mail' | 'express' | 'goods'
  section_id: string
  delay_min:  number
  direction:  'DOWN' | 'UP'
  speed_kmh:  number
}

export interface Disruption {
  disruption_id: string
  type:          string
  status:        string
  section_id:    string | null
  duration_min:  number
}

export interface Snapshot {
  tick:         number
  trains:       TrainPosition[]
  disruptions:  Disruption[]
  metrics:      Record<string, number>
}

export interface SimStatus {
  session_id:    string
  status:        'running' | 'paused' | 'stopped'
  tick:          number
  wall_time_s:   number
  n_trains:      number
  n_disruptions: number
}

// ── Prediction ───────────────────────────────────────────────────────────────

export interface DelayPrediction {
  train_id:   string
  section_id: string
  pred_30:    number | null
  pred_60:    number | null
  pred_120:   number | null
  model_used: string
}

export interface SectionCongestion {
  section_id:          string
  congestion_score_h1: number
  congestion_score_h2: number | null
  congestion_score_h3: number | null
  risk_level:          'low' | 'medium' | 'high'
}

// ── Optimization ─────────────────────────────────────────────────────────────

export interface Decision {
  decision_type:   'HOLD' | 'REROUTE' | 'PRECEDENCE' | 'CROSSING' | 'OVERTAKING'
  train_id:        string
  section_id:      string
  detail:          string
  delay_saved_min: number
  hold_minutes:    number
  alt_route:       string[] | null
  affected_trains: string[]
  confidence:      number
}

export interface OptimizationResult {
  status:          string
  decisions:       Decision[]
  baseline_delay:  number
  optimized_delay: number
  delay_saved:     number
  solve_time_sec:  number
  n_conflicts:     number
}

// ── Explainability ────────────────────────────────────────────────────────────

export interface Explanation {
  train_id:   string
  section_id: string
  action:     string
  text:       string
  risk:       string
  confidence: number
  source:     string
  latency_ms: number
}

// ── Corridor geo ─────────────────────────────────────────────────────────────

export interface Station {
  id:    string
  name:  string
  code:  string
  latlng: [number, number]
}

export interface Section {
  id:            string
  from:          string   // station code
  to:            string
  is_single_line: boolean
}

// ── WebSocket ─────────────────────────────────────────────────────────────────

export interface WsFrame {
  type:    'snapshot' | 'disruption' | 'recommendation' | 'error' | 'ping'
  payload: Record<string, unknown>
  tick:    number
}

// ── UI state ──────────────────────────────────────────────────────────────────

export type DisruptionType = 'TRACK_BLOCK' | 'FOG' | 'SIGNAL_FAIL'

export interface ToastMsg {
  id:      number
  kind:    'info' | 'success' | 'warn' | 'error'
  message: string
}
