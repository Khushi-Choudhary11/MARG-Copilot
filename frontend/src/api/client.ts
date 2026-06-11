import axios from 'axios'

const BASE = import.meta.env.VITE_API_URL ?? ''
// When BASE is empty the Vite proxy handles routing, so derive WS base from
// the page origin so the browser opens the socket to the same host (tunnel or
// localhost) and Vite upgrades it to the backend tunnel automatically.
const WS_BASE = BASE
  ? BASE.replace(/^http/, 'ws')
  : `${window.location.protocol === 'https:' ? 'wss' : 'ws'}://${window.location.host}`

export const http = axios.create({ baseURL: BASE, timeout: 10_000 })

// Attach token from localStorage on every request
http.interceptors.request.use(cfg => {
  const tok = localStorage.getItem('marg_token')
  if (tok) cfg.headers.Authorization = `Bearer ${tok}`
  return cfg
})

export function wsUrl(path: string): string {
  const tok = localStorage.getItem('marg_token') ?? ''
  return `${WS_BASE}${path}?token=${tok}`
}

/** Login — returns JWT and stores it. */
export async function login(username: string, password: string): Promise<string> {
  const form = new URLSearchParams({ username, password })
  const { data } = await http.post('/api/v1/auth/token', form, {
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
  })
  const token: string = data.access_token
  localStorage.setItem('marg_token', token)
  http.defaults.headers.common.Authorization = `Bearer ${token}`
  return token
}
