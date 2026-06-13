import axios from "axios";

export const API_BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000";
export const WS_BASE = API_BASE.replace(/^http/, "ws");

export const api = axios.create({ baseURL: API_BASE });

api.interceptors.request.use((config) => {
  const token = localStorage.getItem("auth_token");
  if (token) {
    config.headers = config.headers ?? {};
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

export interface StationOut {
  station_code: string;
  station_name: string;
  latitude: number | null;
  longitude: number | null;
  platforms: number | null;
  main_tracks: number | null;
  loop_lines: number | null;
  station_category: string | null;
}

export interface LiveTrainPosition {
  train_number: string;
  train_name: string | null;
  train_type: string | null;
  priority: number;
  corridor_direction: string | null;
  status: "scheduled" | "running" | "completed";
  from_station: string | null;
  to_station: string | null;
  progress: number;
  latitude: number | null;
  longitude: number | null;
  current_delay: number;
  predicted_delay_next: number | null;
  prediction_source: "model" | "fallback" | null;
  next_station: string | null;
  eta_next: string | null;
}

export interface TwinSnapshot {
  sim_time: string;
  demo_date: string;
  sim_speed: number;
  trains: LiveTrainPosition[];
  stations: StationOut[];
}

export interface Recommendation {
  id: string;
  train_number: string;
  train_name: string | null;
  station_code: string;
  severity: "info" | "warning" | "critical";
  predicted_delay: number;
  prediction_source: string;
  message: string;
  suggested_action: string;
}

export interface KpiSummary {
  sim_time: string;
  demo_date: string;
  total_trains: number;
  running_trains: number;
  avg_current_delay: number;
  avg_predicted_delay: number;
  on_time_pct: number;
  delayed_pct: number;
  model_active: boolean;
  model_name: string;
}

export interface TrainSummary {
  train_number: string;
  train_name: string | null;
  train_type: string | null;
  priority: number;
  corridor_direction: string | null;
  source_station_code: string | null;
  destination_station_code: string | null;
  stops: string[];
}

export interface StopOut {
  station_code: string;
  station_sequence: number;
  scheduled_arrival: string | null;
  scheduled_departure: string | null;
  current_delay: number;
  predicted_delay_next: number | null;
  prediction_source: string | null;
  status: "done" | "current" | "upcoming";
}

export interface TrainDetail extends TrainSummary {
  operating_days: string | null;
  total_distance_km: number | null;
  route_stops: StopOut[];
}

export interface StationDelayStat {
  station_code: string;
  avg_current_delay: number;
  avg_station_historical_delay: number;
  train_count: number;
}

export interface TrainTypeDelay {
  train_type: string;
  avg_delay: number;
}

export type Role = "admin" | "controller" | "viewer";

export interface AuthUser {
  username: string;
  role: Role;
  name: string;
  token: string;
}

export interface ActionLogEntry {
  id: string;
  timestamp: string;
  train_number: string;
  train_name: string | null;
  station_code: string;
  severity: string;
  predicted_delay: number;
  action: string;
  actor: string;
  auto: boolean;
}

export interface AiAskResponse {
  answer: string;
  source: "claude" | "template" | "puter";
}
