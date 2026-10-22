import React from "react"
import { 
  HeartHandshake, 
  Activity, 
  MapPin, 
  Radio, 
  CheckCircle2, 
  AlertTriangle,
  RotateCcw
} from "lucide-react"
import { PersonaProfile, AppState, RoutineItem } from "@/types"

interface AmbientHeroProps {
  persona: PersonaProfile
  appState: AppState
  onResetEscalation: () => void
}

export const AmbientHero: React.FC<AmbientHeroProps> = ({
  persona,
  appState,
  onResetEscalation,
}) => {
  const stage = appState.escalation.stage
  const isNormal = stage === "normal"
  const isGentle = stage === "gentle_checkin"
  const isRepeated = stage === "repeated_checkin"
  const isAlert = stage === "alert_dispatched" || appState.risk.level === "high" || appState.risk.level === "critical"

  // Status styling
  const statusColor = isAlert
    ? "rose"
    : isRepeated
    ? "orange"
    : isGentle
    ? "amber"
    : "emerald"

  // Determine status headline
  let headline = `${persona.name} is safe and on routine.`
  let subStatus = "All scheduled morning baselines completed smoothly."

  if (isAlert) {
    headline = `Safety Escalation Active: Caregiver notification dispatched.`
    subStatus = appState.escalation.reasons[0] || "Inactivity beyond expected grace period."
  } else if (isRepeated) {
    headline = `Second Ambient Check-In in progress.`
    subStatus = "Awaiting response to follow-up Alexa voice prompt."
  } else if (isGentle) {
    headline = `Gentle Check-In sent via ${persona.device}.`
    subStatus = "Alexa asked: 'Good afternoon, are you doing okay?'"
  } else {
    // Normal state - provide reassuring detail
    headline = `${persona.shortName} is resting comfortably & on routine.`
    subStatus = `Living room activity and morning medication confirmed on schedule.`
  }

  // Count routines
  const completedRoutines = persona.routines.filter((r: RoutineItem) => r.completed).length
  const totalRoutines = persona.routines.length
  const adherencePercent = Math.round((completedRoutines / totalRoutines) * 100)

  return (
    <div className="relative overflow-hidden rounded-3xl border border-stone-200/90 dark:border-zinc-800 bg-white/70 dark:bg-zinc-900/60 backdrop-blur-xl shadow-xl shadow-stone-200/50 dark:shadow-none p-5 sm:p-7 transition-all duration-300">
      {/* Background ambient gradient glow */}
      <div
        className={`absolute -top-24 -right-24 w-80 h-80 rounded-full blur-3xl opacity-20 pointer-events-none transition-all duration-500 ${
          statusColor === "emerald"
            ? "bg-emerald-400"
            : statusColor === "amber"
            ? "bg-amber-400"
            : statusColor === "orange"
            ? "bg-orange-400"
            : "bg-rose-500"
        }`}
      />

      <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-6 relative z-10">
        {/* Left: Avatar with glowing ring and name */}
        <div className="flex items-center gap-4 sm:gap-5">
          <div className="relative flex-shrink-0">
            {/* Animated breathing glow ring */}
            <div
              className={`absolute -inset-1.5 rounded-full blur-sm opacity-70 animate-pulse transition-colors duration-500 ${
                statusColor === "emerald"
                  ? "bg-gradient-to-tr from-emerald-400 to-teal-400"
                  : statusColor === "amber"
                  ? "bg-gradient-to-tr from-amber-400 to-yellow-300"
                  : "bg-gradient-to-tr from-rose-500 to-red-600"
              }`}
            />
            <img
              src={persona.photo}
              alt={persona.name}
              className="relative w-20 h-20 sm:w-24 sm:h-24 rounded-full object-cover border-2 border-white dark:border-zinc-800 shadow-md"
            />
            {/* Sensor heartbeat beacon */}
            <div
              className={`absolute bottom-0 right-0 w-6 h-6 rounded-full flex items-center justify-center border-2 border-white dark:border-zinc-900 text-white shadow-sm ${
                statusColor === "emerald" ? "bg-emerald-500" : "bg-amber-500"
              }`}
            >
              <Radio className="w-3.5 h-3.5 animate-pulse" />
            </div>
          </div>

          <div className="space-y-1">
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="text-xl sm:text-2xl font-bold tracking-tight text-stone-900 dark:text-zinc-100">
                {persona.name}
              </h2>
              <span className="text-xs font-semibold px-2 py-0.5 rounded-full bg-stone-100 dark:bg-zinc-800 text-stone-600 dark:text-zinc-300 border border-stone-200 dark:border-zinc-700">
                Age {persona.age}
              </span>
            </div>

            <p className="text-xs sm:text-sm text-stone-500 dark:text-zinc-400 font-medium flex items-center gap-1.5">
              <MapPin className="w-3.5 h-3.5 text-stone-400 flex-shrink-0" />
              <span>{persona.tagline}</span>
            </p>

            <div className="pt-1 flex items-center gap-2">
              <span
                className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold border ${
                  statusColor === "emerald"
                    ? "bg-emerald-50 dark:bg-emerald-950/40 text-emerald-700 dark:text-emerald-400 border-emerald-200 dark:border-emerald-800/60"
                    : statusColor === "amber"
                    ? "bg-amber-50 dark:bg-amber-950/40 text-amber-700 dark:text-amber-400 border-amber-200 dark:border-amber-800/60"
                    : "bg-rose-50 dark:bg-rose-950/40 text-rose-700 dark:text-rose-400 border-rose-200 dark:border-rose-800/60"
                }`}
              >
                {statusColor === "emerald" ? (
                  <CheckCircle2 className="w-3.5 h-3.5" />
                ) : (
                  <AlertTriangle className="w-3.5 h-3.5 animate-bounce" />
                )}
                <span>
                  {isNormal
                    ? "Status: Nominal"
                    : isGentle
                    ? "Stage 1: Gentle Voice Check"
                    : isRepeated
                    ? "Stage 2: Priority Check"
                    : "Stage 3: Family Escalation"}
                </span>
              </span>

              {/* Reset to normal button if escalated */}
              {!isNormal && (
                <button
                  onClick={onResetEscalation}
                  className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-semibold bg-emerald-600 hover:bg-emerald-500 text-white shadow-sm transition-colors"
                  title="Confirm elder is fine and reset escalation state"
                >
                  <RotateCcw className="w-3 h-3" />
                  <span>Confirm All OK</span>
                </button>
              )}
            </div>
          </div>
        </div>

        {/* Right: Glanceable Status Headline Banner */}
        <div className="w-full md:w-auto md:max-w-md bg-stone-50/80 dark:bg-zinc-800/50 border border-stone-200/80 dark:border-zinc-700/60 rounded-2xl p-4 space-y-1">
          <p className="text-xs uppercase tracking-wider font-bold text-sky-600 dark:text-sky-400 flex items-center gap-1.5">
            <Activity className="w-3.5 h-3.5" />
            <span>Ambient Safety Assessment</span>
          </p>
          <p className="text-sm font-semibold text-stone-900 dark:text-zinc-100 leading-snug">
            {headline}
          </p>
          <p className="text-xs text-stone-600 dark:text-zinc-400">
            {subStatus}
          </p>
        </div>
      </div>

      {/* 3 Core Vitals Strip */}
      <div className="mt-6 pt-5 border-t border-stone-100 dark:border-zinc-800/80 grid grid-cols-1 sm:grid-cols-3 gap-3">
        {/* Vital 1: Routine Adherence */}
        <div className="flex items-center gap-3 p-3 rounded-xl bg-stone-50/60 dark:bg-zinc-800/40 border border-stone-200/60 dark:border-zinc-800">
          <div className="w-9 h-9 rounded-lg bg-sky-500/10 text-sky-600 dark:text-sky-400 flex items-center justify-center font-bold text-sm">
            {adherencePercent}%
          </div>
          <div>
            <p className="text-xs font-semibold text-stone-800 dark:text-zinc-200">
              Daily Routines On-Track
            </p>
            <p className="text-[11px] text-stone-500 dark:text-zinc-400">
              {completedRoutines} of {totalRoutines} milestones recorded
            </p>
          </div>
        </div>

        {/* Vital 2: Medication Status */}
        <div className="flex items-center gap-3 p-3 rounded-xl bg-stone-50/60 dark:bg-zinc-800/40 border border-stone-200/60 dark:border-zinc-800">
          <div className="w-9 h-9 rounded-lg bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 flex items-center justify-center">
            <CheckCircle2 className="w-4 h-4" />
          </div>
          <div>
            <p className="text-xs font-semibold text-stone-800 dark:text-zinc-200 truncate">
              {persona.medicationName}
            </p>
            <p className="text-[11px] text-emerald-600 dark:text-emerald-400 font-medium">
              Confirmed Taken On Schedule
            </p>
          </div>
        </div>

        {/* Vital 3: Primary Device / Echo */}
        <div className="flex items-center gap-3 p-3 rounded-xl bg-stone-50/60 dark:bg-zinc-800/40 border border-stone-200/60 dark:border-zinc-800">
          <div className="w-9 h-9 rounded-lg bg-indigo-500/10 text-indigo-600 dark:text-indigo-400 flex items-center justify-center">
            <HeartHandshake className="w-4 h-4" />
          </div>
          <div>
            <p className="text-xs font-semibold text-stone-800 dark:text-zinc-200">
              {persona.device}
            </p>
            <p className="text-[11px] text-stone-500 dark:text-zinc-400">
              Camera-free ambient listening
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}
