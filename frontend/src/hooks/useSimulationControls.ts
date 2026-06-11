import { useCallback, useEffect, useRef } from 'react'
import axios from 'axios'
import { simApi, predApi, optApi } from '../api/endpoints'
import { useStore } from '../store'
import { SECTIONS } from '../data/corridor'
import { login } from '../api/client'
import type { Disruption, SectionCongestion } from '../types'

const PRED_INTERVAL_MS = 15_000   // refresh congestion every 15s
const OPT_INTERVAL_MS  = 30_000   // run optimizer every 30s

export function useSimulationControls() {
  const { setStatus, setCongestion, setDecisions, addImpact,
          addToast, trains, tick } = useStore(s => ({
    setStatus:   s.setStatus,
    setCongestion: s.setCongestion,
    setDecisions:  s.setDecisions,
    addImpact:     s.addImpact,
    addToast:      s.addToast,
    trains:        s.trains,
    tick:          s.tick,
  }))

  const predTimer = useRef<ReturnType<typeof setInterval>>()
  const optTimer  = useRef<ReturnType<typeof setInterval>>()

  // ── Auth + start ──────────────────────────────────────────────────────────

  const initialise = useCallback(async (attempt = 1) => {
    try {
      await login('controller', 'marg2026')
      try {
        const status = await simApi.start('NDLS-CNB', 60, 42)
        setStatus(status)
        addToast('success', 'Simulation started — NDLS→CNB corridor online')
      } catch (e: unknown) {
        if (axios.isAxiosError(e) && e.response?.status === 409) {
          const status = await simApi.status()
          setStatus(status)
          addToast('info', 'Reconnected to running simulation')
        } else {
          throw e
        }
      }
    } catch {
      // Retry up to 5 times with 3s backoff — handles backend not ready yet
      if (attempt < 5) {
        setTimeout(() => initialise(attempt + 1), 3000)
      } else {
        addToast('error', 'Backend unreachable — is the server running on port 8000?')
      }
    }
  }, [setStatus, addToast])

  const handleStop = useCallback(async () => {
    await simApi.stop().catch(() => null)
    clearInterval(predTimer.current)
    clearInterval(optTimer.current)
    addToast('info', 'Simulation stopped')
  }, [addToast])

  const handlePause = useCallback(() =>
    simApi.pause().catch(() => null), [])

  const handleResume = useCallback(() =>
    simApi.resume().catch(() => null), [])

  // ── Disruption injection ──────────────────────────────────────────────────

  const injectDisruption = useCallback(async (
    type: string, section_id?: string, label?: string,
  ) => {
    try {
      await simApi.disrupt(type, section_id)
      addToast('warn', `⚡ ${label ?? type} injected`)
    } catch {
      addToast('error', 'Disruption injection failed')
    }
  }, [addToast])

  // ── Periodic congestion prediction ────────────────────────────────────────

  const refreshCongestion = useCallback(async () => {
    try {
      const sections = await predApi.congestion(
        SECTIONS.map(s => s.id),
        tick % 1440,
      )
      setCongestion(sections)
    } catch { /* silently ignore */ }
  }, [setCongestion, tick])

  // ── Periodic optimizer run ────────────────────────────────────────────────

  const runOptimizer = useCallback(async () => {
    if (trains.length === 0) return
    try {
      const ALL_SECTIONS = SECTIONS.map(s => s.id)   // ['s1','s2','s3','s4','s5']
      const state = useStore.getState()
      const activeDisruptions: Disruption[] = state.disruptions
      const congestion: SectionCongestion[] = state.congestion

      // Build section payload — mark disrupted sections as blocked
      const sectionsPayload: Record<string, unknown> = {}
      SECTIONS.forEach(s => {
        const isBlocked = activeDisruptions.some(
          d => d.type === 'TRACK_BLOCK' && d.section_id === s.id
        )
        const cScore = congestion.find(c => c.section_id === s.id)?.congestion_score_h1 ?? 0.3
        sectionsPayload[s.id] = {
          section_id:      s.id,
          from_station:    s.from,
          to_station:      s.to,
          length_km:       80,
          capacity_per_hr: s.is_single_line ? 40 : 60,
          is_single_line:  s.is_single_line,
          is_blocked:      isBlocked,
          block_duration:  isBlocked ? 30.0 : 0.0,
          congestion_score: cScore,
        }
      })

      // Build train payload — extend remaining_route to end of corridor
      const trainsPayload: Record<string, unknown> = {}
      trains.forEach((t, i) => {
        const idx = ALL_SECTIONS.indexOf(t.section_id)
        const remaining = idx >= 0
          ? (t.direction === 'UP'
              ? ALL_SECTIONS.slice(0, idx + 1).reverse()   // UP: back towards NDLS
              : ALL_SECTIONS.slice(idx))                    // DOWN: forward to CNB
          : ALL_SECTIONS

        const travelTimes: Record<string, number> = {}
        remaining.forEach(sid => { travelTimes[sid] = 45 })

        trainsPayload[t.train_id] = {
          train_id:        t.train_id,
          category:        t.category,
          priority:        i === 0 ? 1 : 2,
          direction:       t.direction,
          current_section: t.section_id,
          current_delay:   t.delay_min,
          sched_dep_min:   480 + i * 30,
          remaining_route: remaining,
          sched_arrivals:  {},
          sched_departures:{},
          travel_times:    travelTimes,
        }
      })

      const result = await optApi.run(trainsPayload, sectionsPayload, tick % 1440)
      if (result.decisions.length > 0) {
        setDecisions(result.decisions)
        addImpact(result.delay_saved, result.baseline_delay)
        addToast('info', `🔧 ${result.decisions.length} recommendation${result.decisions.length > 1 ? 's' : ''} ready`)
      }
    } catch { /* silently ignore */ }
  }, [trains, tick, setDecisions, addImpact, addToast])

  // ── Lifecycle ─────────────────────────────────────────────────────────────

  useEffect(() => {
    initialise()
    predTimer.current = setInterval(refreshCongestion, PRED_INTERVAL_MS)
    optTimer.current  = setInterval(runOptimizer,      OPT_INTERVAL_MS)
    return () => {
      clearInterval(predTimer.current)
      clearInterval(optTimer.current)
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return { handleStop, handlePause, handleResume, injectDisruption }
}
