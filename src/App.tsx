import React, { useState, useEffect, useCallback } from "react"
import { Header } from "@/components/Header"
import { AmbientHero } from "@/components/AmbientHero"
import { PrimaryActions } from "@/components/PrimaryActions"
import { AlexaConsole, MessageItem } from "@/components/AlexaConsole"
import { RoutineSchedule } from "@/components/RoutineSchedule"
import { FamilyCircleModal } from "@/components/FamilyCircleModal"
import { SimulationDrawer } from "@/components/SimulationDrawer"
import { api, PERSONA_PROFILES } from "@/services/api"
import { sound } from "@/services/sound"
import { speech } from "@/services/speech"
import { AppState, PersonaProfile, RoutineItem } from "@/types"

export default function App() {
  const [activePersonaId, setActivePersonaId] = useState<"dad" | "eleanor" | "martha">("dad")
  const [persona, setPersona] = useState<PersonaProfile>(PERSONA_PROFILES["dad"])
  const [speechEnabled, setSpeechEnabled] = useState(speech.isEnabled())
  const [isTestingLabOpen, setIsTestingLabOpen] = useState(false)
  const [isFamilyModalOpen, setIsFamilyModalOpen] = useState(false)
  const [isProcessingVoice, setIsProcessingVoice] = useState(false)

  // Alexa chat messages
  const [messages, setMessages] = useState<MessageItem[]>([
    {
      id: "initial-1",
      sender: "alexa",
      text: "Good morning! Arthur's morning routines are currently nominal. Metoprolol 25mg was recorded at 07:55 AM.",
      timeStr: "08:00 AM",
    },
  ])

  // Application state (synced with backend or local engine)
  const [appState, setAppState] = useState<AppState>({
    clock: {
      utc: "2026-10-20T08:15:00+00:00",
      time_str: "08:15:00 UTC",
      date_str: "2026-10-20",
      display_time: "08:15 AM",
      is_simulated: true,
    },
    escalation: {
      stage: "normal",
      risk_score: 0.0,
      reasons: [],
      last_updated: "2026-10-20T08:15:00+00:00",
    },
    risk: {
      score: 0.0,
      level: "nominal",
      reasons: [],
      anomalies: {
        medication_missed: false,
        no_movement: false,
        odd_hour_activity: false,
        meal_missed: false,
      },
    },
    events_today: [],
    alerts: [],
    isBackendConnected: false,
  })

  // Synchronize state from backend
  const syncState = useCallback(async (personId = activePersonaId) => {
    const isHealthy = await api.checkHealth()
    if (isHealthy) {
      const data = await api.getState(personId)
      if (data) {
        setAppState({
          ...data,
          isBackendConnected: true,
          clock: {
            ...data.clock,
            display_time: data.clock.time_str || "08:15 AM",
          },
        })
        return
      }
    }
    // If backend offline, mark as local mode
    setAppState((prev: AppState) => ({ ...prev, isBackendConnected: false }))
  }, [activePersonaId])

  // Poll state every 4 seconds
  useEffect(() => {
    syncState(activePersonaId)
    const interval = setInterval(() => {
      syncState(activePersonaId)
    }, 4000)
    return () => clearInterval(interval)
  }, [activePersonaId, syncState])

  // Switch persona
  const handleSelectPersona = (id: "dad" | "eleanor" | "martha") => {
    setActivePersonaId(id)
    const newPersona = PERSONA_PROFILES[id]
    setPersona(newPersona)

    // Reset voice message greeting for this persona
    setMessages([
      {
        id: `greeting-${Date.now()}`,
        sender: "alexa",
        text: `Now monitoring ${newPersona.name}. Routines are normal and scheduled check-ins are active.`,
        timeStr: appState.clock.display_time || "Now",
      },
    ])
    syncState(id)
  }

  // Toggle voice speech audio
  const handleToggleSpeech = () => {
    const next = !speechEnabled
    setSpeechEnabled(next)
    speech.setEnabled(next)
  }

  // Handle Ask Alexa Voice prompt
  const handleAskAlexa = async (promptText: string) => {
    const userMsg: MessageItem = {
      id: `user-${Date.now()}`,
      sender: "user",
      text: promptText,
      timeStr: appState.clock.display_time || "Now",
    }
    setMessages((prev: MessageItem[]) => [...prev, userMsg])
    setIsProcessingVoice(true)

    try {
      let voiceReply = ""

      if (appState.isBackendConnected) {
        // Query backend tool
        const lower = promptText.toLowerCase()
        if (lower.includes("summary") || lower.includes("day")) {
          const res = await api.callTool("daily_summary", { person: persona.id })
          voiceReply = res.voiceResponse || "Here is the summary for today's routine."
        } else if (lower.includes("health") || lower.includes("risk") || lower.includes("doing")) {
          const res = await api.callTool("check_routine_health", { person: persona.id })
          voiceReply = res.voiceResponse || `${persona.shortName}'s routine health is normal.`
        } else {
          const res = await api.callTool("ask_memory", { person: persona.id, question: promptText })
          voiceReply = res.voiceResponse || `Yes, ${persona.name}'s events are recorded on track.`
        }
      } else {
        // Intelligent local simulation response
        const lower = promptText.toLowerCase()
        if (lower.includes("pill") || lower.includes("medication")) {
          voiceReply = `Yes, ${persona.name} took their ${persona.medicationName} (${persona.medicationDosage}) on schedule this morning.`
        } else if (lower.includes("lunch") || lower.includes("eat") || lower.includes("meal")) {
          voiceReply = `${persona.shortName} had lunch recorded at 12:21 PM with normal kitchen refrigerator activity.`
        } else if (lower.includes("summary")) {
          voiceReply = `${persona.shortName} had a calm, steady day. Morning routines were on time, movement in living room was normal, and all vitals are nominal.`
        } else {
          voiceReply = `${persona.name} is resting comfortably at home. All scheduled morning checkpoints have been completed.`
        }
      }

      // Append Alexa response
      const alexaMsg: MessageItem = {
        id: `alexa-${Date.now()}`,
        sender: "alexa",
        text: voiceReply,
        timeStr: appState.clock.display_time || "Now",
      }
      setMessages((prev: MessageItem[]) => [...prev, alexaMsg])

      // Speak aloud if speech enabled
      if (speechEnabled) {
        speech.speak(voiceReply)
      }
    } catch {
      const fallbackMsg: MessageItem = {
        id: `alexa-err-${Date.now()}`,
        sender: "alexa",
        text: `Arthur's routine health is nominal today with zero detected anomalies.`,
        timeStr: appState.clock.display_time || "Now",
      }
      setMessages((prev: MessageItem[]) => [...prev, fallbackMsg])
    } finally {
      setIsProcessingVoice(false)
    }
  }

  // Log medication action
  const handleLogMedication = async () => {
    sound.playSuccessChime()
    if (appState.isBackendConnected) {
      await api.callTool("log_routine_event", {
        person: persona.id,
        type: "pill",
        notes: `${persona.medicationName} confirmed taken via UI`,
      })
      await syncState(persona.id)
    }

    // Update local routine checklist
    setPersona((prev: PersonaProfile) => ({
      ...prev,
      routines: prev.routines.map((r: RoutineItem) =>
        r.category === "medication"
          ? { ...r, completed: true, completedTime: appState.clock.display_time }
          : r
      ),
    }))

    // Add confirmation message in Alexa chat
    const msg: MessageItem = {
      id: `log-med-${Date.now()}`,
      sender: "alexa",
      text: `Noted: ${persona.name}'s ${persona.medicationName} is marked taken at ${appState.clock.display_time}.`,
      timeStr: appState.clock.display_time,
    }
    setMessages((prev: MessageItem[]) => [...prev, msg])
  }

  // Log movement action
  const handleLogMovement = async () => {
    sound.playSuccessChime()
    if (appState.isBackendConnected) {
      await api.callTool("log_routine_event", {
        person: persona.id,
        type: "movement",
        notes: "Living room PIR motion registered",
      })
      await syncState(persona.id)
    }

    const msg: MessageItem = {
      id: `log-move-${Date.now()}`,
      sender: "alexa",
      text: `Movement sensor ping registered for ${persona.shortName} in living room. Inactivity timer refreshed.`,
      timeStr: appState.clock.display_time,
    }
    setMessages((prev: MessageItem[]) => [...prev, msg])
  }

  // Toggle routine item in schedule
  const handleToggleRoutine = (id: string) => {
    sound.playSuccessChime()
    setPersona((prev: PersonaProfile) => ({
      ...prev,
      routines: prev.routines.map((r: RoutineItem) => {
        if (r.id === id) {
          const next = !r.completed
          return {
            ...r,
            completed: next,
            completedTime: next ? appState.clock.display_time : undefined,
          }
        }
        return r
      }),
    }))
  }

  // Confirm OK and reset escalation
  const handleResetEscalation = async () => {
    sound.playSuccessChime()
    if (appState.isBackendConnected) {
      await api.callTool("confirm_ok", { person: persona.id })
      await syncState(persona.id)
    } else {
      setAppState((prev: AppState) => ({
        ...prev,
        escalation: {
          ...prev.escalation,
          stage: "normal",
          risk_score: 0.0,
          reasons: [],
        },
      }))
    }
    const msg: MessageItem = {
      id: `reset-${Date.now()}`,
      sender: "alexa",
      text: `${persona.shortName} confirmed they are doing well. Safety escalation has returned to nominal.`,
      timeStr: appState.clock.display_time,
    }
    setMessages((prev: MessageItem[]) => [...prev, msg])
  }

  // Send soft chime to Echo Show
  const handleSendChime = async () => {
    sound.playAlexaChime()
    if (appState.isBackendConnected) {
      await api.callTool("schedule_reminder", {
        person: persona.id,
        text: `Hello ${persona.shortName}, family is checking in softly.`,
        time: "now",
      })
    }
    const msg: MessageItem = {
      id: `chime-${Date.now()}`,
      sender: "alexa",
      text: `Soft ambient chime announced through ${persona.device}.`,
      timeStr: appState.clock.display_time,
    }
    setMessages((prev: MessageItem[]) => [...prev, msg])
  }

  // Dispatch emergency alert
  const handleDispatchAlert = async () => {
    sound.playAlertChime()
    if (appState.isBackendConnected) {
      await api.callTool("notify_family", {
        person: persona.id,
        severity: "warning",
        message: `Manual caregiver priority check requested for ${persona.name}.`,
      })
      await syncState(persona.id)
    } else {
      setAppState((prev: AppState) => ({
        ...prev,
        escalation: {
          ...prev.escalation,
          stage: "alert_dispatched",
          risk_score: 0.8,
          reasons: ["Caregiver manual check-in dispatched via Amazon SNS."],
        },
      }))
    }
  }

  // Simulation Lab actions
  const handleAdvanceClock = async (minutes: number) => {
    sound.playSuccessChime()
    if (appState.isBackendConnected) {
      await api.advanceClock(minutes, persona.id)
      await syncState(persona.id)
    } else {
      setAppState((prev: AppState) => {
        const [h, m] = (prev.clock.display_time || "08:15").split(":")
        const newHour = (parseInt(h || "8", 10) + Math.floor(minutes / 60)) % 24
        const newTime = `${String(newHour).padStart(2, "0")}:${m || "15"}`
        return {
          ...prev,
          clock: {
            ...prev.clock,
            display_time: `${newTime} UTC`,
            time_str: `${newTime}:00 UTC`,
          },
        }
      })
    }
  }

  const handleSetTime = async (timeStr: string) => {
    sound.playSuccessChime()
    if (appState.isBackendConnected) {
      await api.setClockTime(timeStr, persona.id)
      await syncState(persona.id)
    } else {
      setAppState((prev: AppState) => ({
        ...prev,
        clock: {
          ...prev.clock,
          display_time: "02:00 PM",
          time_str: "14:00:00 UTC",
        },
      }))
    }
  }

  const handleResetClock = async () => {
    sound.playSuccessChime()
    if (appState.isBackendConnected) {
      await api.resetClock(persona.id)
      await syncState(persona.id)
    } else {
      setAppState((prev: AppState) => ({
        ...prev,
        clock: {
          ...prev.clock,
          display_time: "08:15 AM",
          time_str: "08:15:00 UTC",
        },
        escalation: {
          stage: "normal",
          risk_score: 0.0,
          reasons: [],
          last_updated: "2026-10-20T08:15:00+00:00",
        },
      }))
    }
  }

  const handleTriggerScenario = async (type: "skips_lunch" | "missed_meds") => {
    sound.playAlertChime()
    if (type === "skips_lunch") {
      if (appState.isBackendConnected) {
        await api.triggerSkipsLunchScenario()
        await syncState(persona.id)
      } else {
        setAppState((prev: AppState) => ({
          ...prev,
          clock: { ...prev.clock, display_time: "02:00 PM", time_str: "14:00:00 UTC" },
          escalation: {
            stage: "gentle_checkin",
            risk_score: 0.5,
            reasons: ["Midday lunch routine window passed with no kitchen sensor activity."],
            last_updated: "2026-10-20T14:00:00+00:00",
          },
        }))
      }
      setMessages((prev: MessageItem[]) => [
        ...prev,
        {
          id: `scen-${Date.now()}`,
          sender: "alexa",
          text: `[Scenario] It is 2:00 PM. ${persona.shortName} hasn't been in the kitchen for lunch. Gentle voice prompt sent to Living Room Echo.`,
          timeStr: "02:00 PM",
        },
      ])
    } else {
      // Missed medication scenario
      setAppState((prev: AppState) => ({
        ...prev,
        escalation: {
          stage: "repeated_checkin",
          risk_score: 0.7,
          reasons: [`${persona.medicationName} morning dose not detected from smart pillbox.`],
          last_updated: "2026-10-20T09:30:00+00:00",
        },
      }))
      setMessages((prev: MessageItem[]) => [
        ...prev,
        {
          id: `scen-med-${Date.now()}`,
          sender: "alexa",
          text: `[Alert] Morning ${persona.medicationName} was not logged. High priority reminder triggered.`,
          timeStr: appState.clock.display_time,
        },
      ])
    }
  }

  const handleResetDemoData = async () => {
    sound.playSuccessChime()
    if (appState.isBackendConnected) {
      await api.resetDemoData()
      await syncState(persona.id)
    }
    setPersona(PERSONA_PROFILES[activePersonaId])
  }

  // Check if medication is already done
  const medicationDone = persona.routines.some(
    (r: RoutineItem) => r.category === "medication" && r.completed
  )

  return (
    <div className="min-h-screen bg-[#f8f7f4] dark:bg-[#080c14] text-stone-900 dark:text-zinc-100 transition-colors duration-200">
      {/* Top Header */}
      <Header
        activePersonaId={activePersonaId}
        onSelectPersona={handleSelectPersona}
        isConnected={appState.isBackendConnected}
        displayTime={appState.clock.display_time || "08:15 AM"}
        speechEnabled={speechEnabled}
        onToggleSpeech={handleToggleSpeech}
        onOpenTestingLab={() => setIsTestingLabOpen(true)}
      />

      {/* Main Content: Clean, focused, uncluttered front page */}
      <main className="max-w-6xl mx-auto px-4 sm:px-6 py-6 sm:py-8 space-y-6 sm:space-y-8">
        {/* 1. Loved One Hero Ambient Peace of Mind Status */}
        <AmbientHero
          persona={persona}
          appState={appState}
          onResetEscalation={handleResetEscalation}
        />

        {/* 2. Exactly 4 Simple, Clear Quick Action Tiles in Front */}
        <PrimaryActions
          persona={persona}
          onAskAlexa={handleAskAlexa}
          onLogMedication={handleLogMedication}
          onLogMovement={handleLogMovement}
          onOpenFamilyCall={() => setIsFamilyModalOpen(true)}
          medicationDone={medicationDone}
        />

        {/* 3. Core Daily Routine Schedule & Ambient Alexa Companion */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 items-start">
          {/* Daily Schedule Checklist */}
          <RoutineSchedule
            routines={persona.routines}
            onToggleRoutine={handleToggleRoutine}
            personName={persona.name}
          />

          {/* Interactive Ambient Alexa+ Console */}
          <AlexaConsole
            persona={persona}
            messages={messages}
            onSendMessage={handleAskAlexa}
            isProcessing={isProcessingVoice}
            onClearHistory={() => setMessages([])}
          />
        </div>

        {/* Subtle Bottom Bar: Simulator & Testing Lab launcher */}
        <div className="pt-4 border-t border-stone-200/60 dark:border-zinc-800/80 flex flex-col sm:flex-row items-center justify-between text-xs text-stone-500 dark:text-zinc-400 gap-3">
          <div className="flex items-center gap-2">
            <span
              className={`w-2 h-2 rounded-full ${
                appState.isBackendConnected ? "bg-emerald-500" : "bg-amber-500"
              }`}
            />
            <span>
              {appState.isBackendConnected
                ? "FastMCP Streamable HTTP Server Live (/mcp)"
                : "Local Circadian Simulation Active"}
            </span>
          </div>

          <div className="flex items-center gap-3">
            <button
              onClick={() => setIsTestingLabOpen(true)}
              className="text-sky-600 dark:text-sky-400 font-semibold hover:underline"
            >
              Advance Clock & Scenarios Lab &rarr;
            </button>
            <span>&bull;</span>
            <a
              href="/simulator"
              target="_blank"
              rel="noreferrer"
              className="hover:underline"
            >
              Raw Developer Cockpit
            </a>
          </div>
        </div>
      </main>

      {/* Family Circle Contact Modal */}
      <FamilyCircleModal
        isOpen={isFamilyModalOpen}
        onClose={() => setIsFamilyModalOpen(false)}
        persona={persona}
        onSendChime={handleSendChime}
        onDispatchAlert={handleDispatchAlert}
      />

      {/* Simulator Lab Drawer */}
      <SimulationDrawer
        isOpen={isTestingLabOpen}
        onClose={() => setIsTestingLabOpen(false)}
        onAdvanceClock={handleAdvanceClock}
        onSetTime={handleSetTime}
        onResetClock={handleResetClock}
        onTriggerScenario={handleTriggerScenario}
        onResetDemoData={handleResetDemoData}
        clockUtc={appState.clock.time_str || "08:15:00 UTC"}
        isBackendConnected={appState.isBackendConnected}
      />
    </div>
  )
}
