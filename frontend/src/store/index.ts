import { create } from 'zustand'
import type {
  TrainPosition, Disruption, SectionCongestion,
  Decision, Explanation, ToastMsg, SimStatus,
} from '../types'

// ── Simulation slice ──────────────────────────────────────────────────────────

interface SimSlice {
  status:       SimStatus | null
  trains:       TrainPosition[]
  disruptions:  Disruption[]
  metrics:      Record<string, number>
  tick:         number
  connected:    boolean
  setStatus:    (s: SimStatus) => void
  applySnapshot:(payload: { trains: TrainPosition[]; disruptions: Disruption[]; metrics: Record<string, number>; tick: number }) => void
  setConnected: (v: boolean) => void
}

// ── Prediction slice ──────────────────────────────────────────────────────────

interface PredSlice {
  congestion:      SectionCongestion[]
  setCongestion:   (v: SectionCongestion[]) => void
}

// ── Optimization slice ────────────────────────────────────────────────────────

interface OptSlice {
  decisions:        Decision[]
  explanations:     Record<string, Explanation>  // keyed by train_id+section_id
  delaySaved:       number                        // cumulative impact counter
  baselineDelay:    number
  setDecisions:     (d: Decision[]) => void
  addExplanation:   (key: string, e: Explanation) => void
  acceptDecision:   (idx: number) => void
  overrideDecision: (idx: number) => void
  addImpact:        (saved: number, baseline: number) => void
}

// ── Toast slice ───────────────────────────────────────────────────────────────

interface ToastSlice {
  toasts:     ToastMsg[]
  addToast:   (kind: ToastMsg['kind'], message: string) => void
  removeToast:(id: number) => void
}

// ── Combined store ────────────────────────────────────────────────────────────

type Store = SimSlice & PredSlice & OptSlice & ToastSlice

let _toastId = 0

export const useStore = create<Store>((set, get) => ({
  // ── Simulation ─────────────────────────────────────────────────────────────
  status:      null,
  trains:      [],
  disruptions: [],
  metrics:     {},
  tick:        0,
  connected:   false,

  setStatus:   (s) => set({ status: s }),
  setConnected:(v) => set({ connected: v }),

  applySnapshot: ({ trains, disruptions, metrics, tick }) =>
    set({ trains, disruptions, metrics, tick }),

  // ── Prediction ─────────────────────────────────────────────────────────────
  congestion:    [],
  setCongestion: (v) => set({ congestion: v }),

  // ── Optimization ───────────────────────────────────────────────────────────
  decisions:    [],
  explanations: {},
  delaySaved:   0,
  baselineDelay: 0,

  setDecisions: (d) => set({ decisions: d }),

  addExplanation: (key, e) =>
    set(s => ({ explanations: { ...s.explanations, [key]: e } })),

  acceptDecision: (idx) =>
    set(s => ({
      decisions: s.decisions.filter((_, i) => i !== idx),
    })),

  overrideDecision: (idx) =>
    set(s => ({
      decisions: s.decisions.map((d, i) =>
        i === idx ? { ...d, _overridden: true } as Decision : d),
    })),

  addImpact: (saved, baseline) =>
    set(s => ({
      delaySaved:    s.delaySaved    + saved,
      baselineDelay: s.baselineDelay + baseline,
    })),

  // ── Toasts ─────────────────────────────────────────────────────────────────
  toasts: [],

  addToast: (kind, message) => {
    const id = ++_toastId
    set(s => ({ toasts: [...s.toasts, { id, kind, message }] }))
    setTimeout(() => get().removeToast(id), 4000)
  },

  removeToast: (id) =>
    set(s => ({ toasts: s.toasts.filter(t => t.id !== id) })),
}))
