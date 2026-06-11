import { http } from './client'
import type {
  SimStatus, Decision, OptimizationResult,
  DelayPrediction, SectionCongestion, Explanation,
} from '../types'

// ── Simulation ────────────────────────────────────────────────────────────────

export const simApi = {
  start: (corridor = 'NDLS-CNB', speedFactor = 60, seed = 42) =>
    http.post<SimStatus>('/api/v1/simulation/start', {
      corridor, speed_factor: speedFactor, seed, disruptions: true,
    }).then(r => r.data),

  stop:   () => http.post('/api/v1/simulation/stop').then(r => r.data),
  pause:  () => http.post('/api/v1/simulation/pause').then(r => r.data),
  resume: () => http.post('/api/v1/simulation/resume').then(r => r.data),
  status: () => http.get<SimStatus>('/api/v1/simulation/status').then(r => r.data),

  disrupt: (type: string, section_id?: string, duration_min = 45, severity = 1.0) =>
    http.post('/api/v1/simulation/disrupt', {
      type, section_id, duration_min, severity,
    }).then(r => r.data),
}

// ── Prediction ────────────────────────────────────────────────────────────────

export const predApi = {
  delay: (train_id: string, section_id: string, current_delay_min = 0) =>
    http.post<DelayPrediction>('/api/v1/prediction/delay', {
      train_id, section_id, current_delay_min,
      priority: 2, category: 'express', weather: 'CLEAR',
      congestion_score: 0.3, sched_depart_min: 600,
    }).then(r => r.data),

  congestion: (section_ids: string[], timestamp_min = 600) =>
    http.post<{ sections: SectionCongestion[] }>('/api/v1/prediction/congestion', {
      section_ids, horizon_hours: 1, timestamp_min,
    }).then(r => r.data.sections),
}

// ── Optimization ──────────────────────────────────────────────────────────────

export const optApi = {
  run: (
    trains: Record<string, unknown>,
    sections: Record<string, unknown>,
    timestamp_min: number,
  ) =>
    http.post<OptimizationResult>('/api/v1/optimization/run', {
      timestamp_min, horizon_min: 120,
      trains, sections, min_headway: 3,
    }).then(r => r.data),
}

// ── Explainability ────────────────────────────────────────────────────────────

export const explApi = {
  explain: (decision: Decision) =>
    http.post<Explanation>('/api/v1/explainability/explain', {
      decision_type:   decision.decision_type,
      train_id:        decision.train_id,
      section_id:      decision.section_id,
      detail:          decision.detail,
      delay_saved_min: decision.delay_saved_min,
      hold_minutes:    decision.hold_minutes,
      affected_trains: decision.affected_trains,
      confidence:      decision.confidence,
    }).then(r => r.data),
}
