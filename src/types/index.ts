export interface EmergencyContact {
  name: string
  relationship: string
  phone: string
}

export interface RoutineItem {
  id: string
  title: string
  timeStr: string
  category: "medication" | "meal" | "movement" | "door" | "checkin"
  sensor: string
  completed: boolean
  completedTime?: string
  notes?: string
}

export interface PersonaProfile {
  id: "dad" | "eleanor" | "martha"
  name: string
  shortName: string
  age: number
  tagline: string
  location: string
  device: string
  photo: string
  emergencyContacts: EmergencyContact[]
  routines: RoutineItem[]
  medicationName: string
  medicationDosage: string
}

export interface EventRecord {
  event_id: string
  type: string
  time: string
  timestamp: string
  metadata?: Record<string, any>
}

export interface AlertRecord {
  alert_id: string
  level: "info" | "warning" | "alert" | "critical"
  title: string
  reasons: string[]
  status: "active" | "resolved" | "acknowledged"
  created_at: string
  time_str: string
}

export interface SystemStatus {
  database: { type: string; path?: string }
  server: { status: string; version: string; clock_mode: string }
  notifier: { type: string }
}

export interface AppState {
  clock: {
    utc: string
    time_str: string
    date_str: string
    is_simulated: boolean
    display_time: string
  }
  escalation: {
    stage: "normal" | "gentle_checkin" | "repeated_checkin" | "alert_dispatched"
    risk_score: number
    reasons: string[]
    last_updated: string
  }
  risk: {
    score: number
    level: "nominal" | "low" | "medium" | "high" | "critical"
    reasons: string[]
    anomalies: {
      medication_missed: boolean
      no_movement: boolean
      odd_hour_activity: boolean
      meal_missed: boolean
    }
  }
  events_today: EventRecord[]
  alerts: AlertRecord[]
  isBackendConnected: boolean
}
