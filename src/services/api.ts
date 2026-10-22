import { AppState, PersonaProfile, RoutineItem } from "@/types"

export const PERSONA_PROFILES: Record<string, PersonaProfile> = {
  dad: {
    id: "dad",
    name: "Arthur Davis",
    shortName: "Dad",
    age: 81,
    tagline: "Retired Navy Veteran · Independent Living",
    location: "Silver Spring, MD (Apartment 4B)",
    device: "Living Room Echo Show 10",
    photo: "/portraits/arthur.jpg",
    medicationName: "Metoprolol Tartrate",
    medicationDosage: "25mg Morning Beta-Blocker",
    emergencyContacts: [
      { name: "Linda Davis", relationship: "Daughter (Primary Caregiver)", phone: "+1 (555) 019-2834" },
      { name: "Mark Davis", relationship: "Son", phone: "+1 (555) 019-5847" },
    ],
    routines: [
      {
        id: "wake",
        title: "Morning Wake & Gentle Stretch",
        timeStr: "07:00 AM",
        category: "movement",
        sensor: "Bedroom PIR Motion Sensor",
        completed: true,
        completedTime: "06:55 AM",
        notes: "Bedroom sensor detected gentle movement",
      },
      {
        id: "medication",
        title: "Prescription Heart Beta-Blocker",
        timeStr: "08:00 AM",
        category: "medication",
        sensor: "Smart Pillbox Tray 1",
        completed: true,
        completedTime: "07:55 AM",
        notes: "Metoprolol 25mg confirmed taken",
      },
      {
        id: "garden",
        title: "Patio Walk & Garden Check",
        timeStr: "11:15 AM",
        category: "door",
        sensor: "Patio Door Contact Sensor",
        completed: true,
        completedTime: "11:19 AM",
        notes: "Exterior patio door opened & closed safely",
      },
      {
        id: "lunch",
        title: "Midday Meal & Hydration",
        timeStr: "12:30 PM",
        category: "meal",
        sensor: "Kitchen Refrigerator & PIR",
        completed: true,
        completedTime: "12:21 PM",
        notes: "Microwave & refrigerator activity recorded",
      },
      {
        id: "evening",
        title: "Evening Wind-Down & Check-In",
        timeStr: "07:30 PM",
        category: "checkin",
        sensor: "Living Room Echo Show",
        completed: false,
        notes: "Scheduled ambient conversational check-in",
      },
    ],
  },
  eleanor: {
    id: "eleanor",
    name: "Eleanor Davis",
    shortName: "Mom",
    age: 78,
    tagline: "Retired Botanist · Early Riser",
    location: "Annapolis, MD (Cottage)",
    device: "Kitchen Echo Show 8",
    photo: "/portraits/eleanor.jpg",
    medicationName: "Lisinopril & Vitamin D3",
    medicationDosage: "10mg Morning Regimen",
    emergencyContacts: [
      { name: "Linda Davis", relationship: "Daughter", phone: "+1 (555) 019-2834" },
      { name: "Dr. Robert Vance", relationship: "Primary Physician", phone: "+1 (555) 012-9981" },
    ],
    routines: [
      {
        id: "wake",
        title: "Early Wake & Morning Tea",
        timeStr: "07:15 AM",
        category: "movement",
        sensor: "Kitchen Electric Kettle & PIR",
        completed: true,
        completedTime: "07:18 AM",
        notes: "Kitchen kettle powered on",
      },
      {
        id: "medication",
        title: "Blood Pressure Regimen (Lisinopril)",
        timeStr: "08:15 AM",
        category: "medication",
        sensor: "Smart Pillbox Tray 2",
        completed: true,
        completedTime: "08:12 AM",
        notes: "Dispenser opened and pill taken",
      },
      {
        id: "garden",
        title: "Sunroom Plants & Gardening",
        timeStr: "10:30 AM",
        category: "movement",
        sensor: "Sunroom Motion Sensor",
        completed: true,
        completedTime: "10:35 AM",
        notes: "Normal activity in sunroom",
      },
      {
        id: "lunch",
        title: "Nutritious Lunch & Water Intake",
        timeStr: "01:00 PM",
        category: "meal",
        sensor: "Dining Area Sensor",
        completed: false,
        notes: "Scheduled lunch window",
      },
      {
        id: "evening",
        title: "Classical Music & Evening Calm",
        timeStr: "08:00 PM",
        category: "checkin",
        sensor: "Echo Show 8",
        completed: false,
        notes: "Alexa ambient evening routine",
      },
    ],
  },
  martha: {
    id: "martha",
    name: "Martha Jenkins",
    shortName: "Martha",
    age: 84,
    tagline: "Late Riser · Gentle Chime Reminders",
    location: "Oakwood Assisted Community",
    device: "Bedside Echo Dot",
    photo: "/portraits/martha.jpg",
    medicationName: "Amlodipine Besylate",
    medicationDosage: "5mg Mid-Morning Tablet",
    emergencyContacts: [
      { name: "Robert Jenkins", relationship: "Son", phone: "+1 (555) 014-4412" },
      { name: "Sarah Miller", relationship: "Community Health Aide", phone: "+1 (555) 018-7723" },
    ],
    routines: [
      {
        id: "wake",
        title: "Morning Wake & Room Lights",
        timeStr: "08:15 AM",
        category: "movement",
        sensor: "Smart Bedside Lamp & Sensor",
        completed: true,
        completedTime: "08:20 AM",
        notes: "Bedside lamp turned on",
      },
      {
        id: "medication",
        title: "Blood Pressure Tablet (Amlodipine)",
        timeStr: "09:00 AM",
        category: "medication",
        sensor: "Smart Pillbox Tray 1",
        completed: true,
        completedTime: "08:58 AM",
        notes: "Taken with warm water",
      },
      {
        id: "hallway",
        title: "Morning Community Walk",
        timeStr: "11:30 AM",
        category: "door",
        sensor: "Suite Entrance Sensor",
        completed: true,
        completedTime: "11:28 AM",
        notes: "Suite door opened for walk",
      },
      {
        id: "lunch",
        title: "Lunch at Community Dining Room",
        timeStr: "12:45 PM",
        category: "meal",
        sensor: "Pendant Check-In",
        completed: false,
        notes: "Due in dining hall",
      },
      {
        id: "evening",
        title: "Family Phone Call & Storytime",
        timeStr: "06:30 PM",
        category: "checkin",
        sensor: "Echo Dot Audio Check",
        completed: false,
        notes: "Weekly family video/audio sync",
      },
    ],
  },
}

class CareLoopAPI {
  // Check if live backend server is healthy
  async checkHealth(): Promise<boolean> {
    try {
      const res = await fetch("/health", { signal: AbortSignal.timeout(1800) })
      return res.ok
    } catch {
      return false
    }
  }

  // Fetch full state for active persona
  async getState(personId: string = "dad"): Promise<AppState | null> {
    try {
      const res = await fetch(`/api/state?person=${encodeURIComponent(personId)}`, {
        signal: AbortSignal.timeout(2500),
      })
      if (!res.ok) return null
      const data = await res.json()
      return {
        ...data,
        isBackendConnected: true,
        clock: {
          ...data.clock,
          display_time: data.clock?.time_str || "08:15 AM",
        },
      }
    } catch {
      return null
    }
  }

  // Call MCP Tool via Streamable HTTP Gateway
  async callTool(tool: string, args: Record<string, any> = {}): Promise<{
    success: boolean
    voiceResponse?: string
    data?: any
    error?: string
  }> {
    try {
      const res = await fetch("/api/mcp/call", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tool, arguments: args }),
        signal: AbortSignal.timeout(8000),
      })
      if (!res.ok) {
        const errJson = await res.json().catch(() => ({}))
        return { success: false, error: errJson.error?.message || errJson.error || "Tool call failed" }
      }
      const data = await res.json()
      if (data.is_error) {
        return { success: false, error: data.error?.message || "Tool returned an error" }
      }
      const voice = data.result?.voice_response || data.result?.answer || data.raw_text
      return {
        success: true,
        voiceResponse: voice,
        data: data.result,
      }
    } catch (err: any) {
      return { success: false, error: err.message || "Network request failed" }
    }
  }

  // Advance simulation clock
  async advanceClock(minutes: number = 60, personId: string = "dad"): Promise<boolean> {
    try {
      const res = await fetch("/api/clock/advance", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ minutes, person: personId }),
        signal: AbortSignal.timeout(3000),
      })
      return res.ok
    } catch {
      return false
    }
  }

  // Reset clock to base time
  async resetClock(personId: string = "dad"): Promise<boolean> {
    try {
      const res = await fetch("/api/clock/reset", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ person: personId }),
        signal: AbortSignal.timeout(3000),
      })
      return res.ok
    } catch {
      return false
    }
  }

  // Set clock to specific time
  async setClockTime(time: string, personId: string = "dad"): Promise<boolean> {
    try {
      const res = await fetch("/api/clock/set", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ time, person: personId }),
        signal: AbortSignal.timeout(3000),
      })
      return res.ok
    } catch {
      return false
    }
  }

  // Trigger Dad Skips Lunch scenario
  async triggerSkipsLunchScenario(): Promise<boolean> {
    try {
      const res = await fetch("/api/demo/skips-lunch/setup", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
        signal: AbortSignal.timeout(4000),
      })
      return res.ok
    } catch {
      return false
    }
  }

  // Reset demo data
  async resetDemoData(): Promise<boolean> {
    try {
      const res = await fetch("/api/demo/reset", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
        signal: AbortSignal.timeout(4000),
      })
      return res.ok
    } catch {
      return false
    }
  }
}

export const api = new CareLoopAPI()
