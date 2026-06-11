import { useEffect, useRef, useCallback } from 'react'
import { wsUrl } from '../api/client'
import { useStore } from '../store'
import type { WsFrame } from '../types'

const RECONNECT_MS = 3000

export function useSimulationWs() {
  const wsRef        = useRef<WebSocket | null>(null)
  const timerRef     = useRef<ReturnType<typeof setTimeout>>()
  const applySnapshot = useStore(s => s.applySnapshot)
  const setConnected  = useStore(s => s.setConnected)
  const addToast      = useStore(s => s.addToast)

  const connect = useCallback(() => {
    // Wait until login() has stored a token; retry until it appears.
    if (!localStorage.getItem('marg_token')) {
      timerRef.current = setTimeout(connect, RECONNECT_MS)
      return
    }
    const url = wsUrl('/api/v1/simulation/ws')
    const ws  = new WebSocket(url)
    wsRef.current = ws

    ws.onopen = () => {
      setConnected(true)
      // keepalive ping every 20s
      const ping = setInterval(() => {
        if (ws.readyState === WebSocket.OPEN)
          ws.send(JSON.stringify({ type: 'ping' }))
      }, 20_000)
      ws.onclose = () => clearInterval(ping)
    }

    ws.onmessage = (ev) => {
      try {
        const frame = JSON.parse(ev.data) as WsFrame
        if (frame.type === 'snapshot') {
          const p = frame.payload as {
            trains: Parameters<typeof applySnapshot>[0]['trains']
            disruptions: Parameters<typeof applySnapshot>[0]['disruptions']
            metrics: Parameters<typeof applySnapshot>[0]['metrics']
            tick: number
          }
          applySnapshot({
            trains:      p.trains      ?? [],
            disruptions: p.disruptions ?? [],
            metrics:     p.metrics     ?? {},
            tick:        frame.tick    ?? 0,
          })
        }
      } catch { /* ignore malformed */ }
    }

    ws.onerror = () => {
      setConnected(false)
    }

    ws.onclose = () => {
      setConnected(false)
      timerRef.current = setTimeout(connect, RECONNECT_MS)
    }
  }, [applySnapshot, setConnected, addToast])

  useEffect(() => {
    connect()
    return () => {
      clearTimeout(timerRef.current)
      wsRef.current?.close()
    }
  }, [connect])
}
