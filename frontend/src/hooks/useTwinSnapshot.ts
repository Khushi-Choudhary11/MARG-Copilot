import { useEffect, useRef, useState } from "react";
import { API_BASE, WS_BASE, type TwinSnapshot } from "../api";

export function useTwinSnapshot() {
  const [snapshot, setSnapshot] = useState<TwinSnapshot | null>(null);
  const [connected, setConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    let cancelled = false;
    let retryTimer: ReturnType<typeof setTimeout>;

    // Initial REST fetch so the UI has data before the socket connects.
    fetch(`${API_BASE}/api/twin/snapshot`)
      .then((r) => r.json())
      .then((data) => {
        if (!cancelled) setSnapshot(data);
      })
      .catch(() => {});

    function connect() {
      const ws = new WebSocket(`${WS_BASE}/api/twin/ws`);
      wsRef.current = ws;
      ws.onopen = () => setConnected(true);
      ws.onmessage = (ev) => {
        try {
          setSnapshot(JSON.parse(ev.data));
        } catch {
          /* ignore */
        }
      };
      ws.onclose = () => {
        setConnected(false);
        if (!cancelled) retryTimer = setTimeout(connect, 2000);
      };
      ws.onerror = () => ws.close();
    }
    connect();

    return () => {
      cancelled = true;
      clearTimeout(retryTimer);
      wsRef.current?.close();
    };
  }, []);

  return { snapshot, connected };
}
