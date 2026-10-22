import React, { useState } from "react"
import { 
  Mic, 
  Pill, 
  Footprints, 
  PhoneCall, 
  Check, 
  Sparkles,
  Loader2
} from "lucide-react"
import { PersonaProfile } from "@/types"

interface PrimaryActionsProps {
  persona: PersonaProfile
  onAskAlexa: (prompt: string) => void
  onLogMedication: () => Promise<void>
  onLogMovement: () => Promise<void>
  onOpenFamilyCall: () => void
  medicationDone: boolean
}

export const PrimaryActions: React.FC<PrimaryActionsProps> = ({
  persona,
  onAskAlexa,
  onLogMedication,
  onLogMovement,
  onOpenFamilyCall,
  medicationDone,
}) => {
  const [loadingMed, setLoadingMed] = useState(false)
  const [loadingMove, setLoadingMove] = useState(false)
  const [justLoggedMed, setJustLoggedMed] = useState(false)
  const [justLoggedMove, setJustLoggedMove] = useState(false)

  const handleMedClick = async () => {
    if (loadingMed) return
    setLoadingMed(true)
    await onLogMedication()
    setLoadingMed(false)
    setJustLoggedMed(true)
    setTimeout(() => setJustLoggedMed(false), 2500)
  }

  const handleMoveClick = async () => {
    if (loadingMove) return
    setLoadingMove(true)
    await onLogMovement()
    setLoadingMove(false)
    setJustLoggedMove(true)
    setTimeout(() => setJustLoggedMove(false), 2500)
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-bold tracking-tight text-stone-900 dark:text-zinc-100 flex items-center gap-2">
          <Sparkles className="w-4 h-4 text-sky-500" />
          <span>Quick Care Actions</span>
        </h3>
        <span className="text-xs text-stone-500 dark:text-zinc-400">
          One-tap ambient updates
        </span>
      </div>

      {/* Grid of exactly 4 clear, beautiful action cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Action 1: Ask Alexa */}
        <div
          onClick={() => onAskAlexa(`Alexa, how is ${persona.shortName} doing right now?`)}
          className="group relative p-4 rounded-2xl border border-sky-200/80 dark:border-sky-900/40 bg-gradient-to-b from-sky-50/70 to-white/90 dark:from-sky-950/20 dark:to-zinc-900/70 hover:border-sky-400 dark:hover:border-sky-500 hover:shadow-lg hover:shadow-sky-500/10 transition-all duration-200 cursor-pointer flex flex-col justify-between"
          role="button"
          tabIndex={0}
        >
          <div className="flex items-start justify-between">
            <div className="w-11 h-11 rounded-xl bg-gradient-to-tr from-sky-500 to-cyan-400 text-white flex items-center justify-center shadow-md shadow-sky-500/25 group-hover:scale-105 transition-transform">
              <Mic className="w-5 h-5" />
            </div>
            <span className="text-[10px] uppercase font-bold tracking-wider px-2 py-0.5 rounded-full bg-sky-500/10 text-sky-600 dark:text-sky-400 border border-sky-500/20">
              Voice
            </span>
          </div>

          <div className="mt-4 space-y-1">
            <h4 className="text-sm font-bold text-stone-900 dark:text-zinc-100 group-hover:text-sky-600 dark:group-hover:text-sky-400 transition-colors">
              Ask Alexa+ Voice
            </h4>
            <p className="text-xs text-stone-500 dark:text-zinc-400 leading-snug">
              Check health, pills, or check in via voice
            </p>
          </div>

          <div className="mt-3 pt-2.5 border-t border-sky-100 dark:border-zinc-800 flex items-center justify-between text-xs font-semibold text-sky-600 dark:text-sky-400">
            <span>&ldquo;How is {persona.shortName}?&rdquo;</span>
            <span className="text-base group-hover:translate-x-0.5 transition-transform">&rarr;</span>
          </div>
        </div>

        {/* Action 2: Log Medication */}
        <div
          onClick={handleMedClick}
          className={`group relative p-4 rounded-2xl border transition-all duration-200 cursor-pointer flex flex-col justify-between ${
            medicationDone || justLoggedMed
              ? "border-emerald-200/80 dark:border-emerald-900/40 bg-gradient-to-b from-emerald-50/70 to-white/90 dark:from-emerald-950/20 dark:to-zinc-900/70"
              : "border-stone-200/80 dark:border-zinc-800 bg-white/90 dark:bg-zinc-900/70 hover:border-emerald-400 dark:hover:border-emerald-500 hover:shadow-lg hover:shadow-emerald-500/10"
          }`}
          role="button"
          tabIndex={0}
        >
          <div className="flex items-start justify-between">
            <div
              className={`w-11 h-11 rounded-xl text-white flex items-center justify-center shadow-md transition-transform group-hover:scale-105 ${
                medicationDone || justLoggedMed
                  ? "bg-gradient-to-tr from-emerald-500 to-teal-400 shadow-emerald-500/25"
                  : "bg-gradient-to-tr from-amber-500 to-orange-400 shadow-amber-500/25"
              }`}
            >
              {loadingMed ? (
                <Loader2 className="w-5 h-5 animate-spin" />
              ) : medicationDone || justLoggedMed ? (
                <Check className="w-5 h-5" />
              ) : (
                <Pill className="w-5 h-5" />
              )}
            </div>
            <span
              className={`text-[10px] uppercase font-bold tracking-wider px-2 py-0.5 rounded-full border ${
                medicationDone || justLoggedMed
                  ? "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/20"
                  : "bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/20"
              }`}
            >
              {medicationDone || justLoggedMed ? "Taken ✓" : "Due"}
            </span>
          </div>

          <div className="mt-4 space-y-1">
            <h4 className="text-sm font-bold text-stone-900 dark:text-zinc-100 group-hover:text-emerald-600 dark:group-hover:text-emerald-400 transition-colors">
              {medicationDone || justLoggedMed ? "Pills Recorded" : "Log Medication"}
            </h4>
            <p className="text-xs text-stone-500 dark:text-zinc-400 leading-snug truncate">
              {persona.medicationName} ({persona.medicationDosage.split(" ")[0]})
            </p>
          </div>

          <div className="mt-3 pt-2.5 border-t border-stone-100 dark:border-zinc-800 flex items-center justify-between text-xs font-semibold text-emerald-600 dark:text-emerald-400">
            <span>{medicationDone || justLoggedMed ? "Confirmed taken" : "Tap to record taken"}</span>
            <span className="text-base group-hover:translate-x-0.5 transition-transform">&rarr;</span>
          </div>
        </div>

        {/* Action 3: Log Movement */}
        <div
          onClick={handleMoveClick}
          className={`group relative p-4 rounded-2xl border transition-all duration-200 cursor-pointer flex flex-col justify-between ${
            justLoggedMove
              ? "border-teal-200/80 dark:border-teal-900/40 bg-gradient-to-b from-teal-50/70 to-white/90 dark:from-teal-950/20 dark:to-zinc-900/70"
              : "border-stone-200/80 dark:border-zinc-800 bg-white/90 dark:bg-zinc-900/70 hover:border-teal-400 dark:hover:border-teal-500 hover:shadow-lg hover:shadow-teal-500/10"
          }`}
          role="button"
          tabIndex={0}
        >
          <div className="flex items-start justify-between">
            <div className="w-11 h-11 rounded-xl bg-gradient-to-tr from-teal-500 to-emerald-400 text-white flex items-center justify-center shadow-md shadow-teal-500/25 group-hover:scale-105 transition-transform">
              {loadingMove ? (
                <Loader2 className="w-5 h-5 animate-spin" />
              ) : justLoggedMove ? (
                <Check className="w-5 h-5" />
              ) : (
                <Footprints className="w-5 h-5" />
              )}
            </div>
            <span className="text-[10px] uppercase font-bold tracking-wider px-2 py-0.5 rounded-full bg-teal-500/10 text-teal-600 dark:text-teal-400 border border-teal-500/20">
              Sensor
            </span>
          </div>

          <div className="mt-4 space-y-1">
            <h4 className="text-sm font-bold text-stone-900 dark:text-zinc-100 group-hover:text-teal-600 dark:group-hover:text-teal-400 transition-colors">
              {justLoggedMove ? "Motion Logged" : "Record Motion"}
            </h4>
            <p className="text-xs text-stone-500 dark:text-zinc-400 leading-snug">
              Living room or kitchen PIR sensor ping
            </p>
          </div>

          <div className="mt-3 pt-2.5 border-t border-stone-100 dark:border-zinc-800 flex items-center justify-between text-xs font-semibold text-teal-600 dark:text-teal-400">
            <span>{justLoggedMove ? "Activity refreshed" : "Tap to record motion"}</span>
            <span className="text-base group-hover:translate-x-0.5 transition-transform">&rarr;</span>
          </div>
        </div>

        {/* Action 4: Family Circle / Call */}
        <div
          onClick={onOpenFamilyCall}
          className="group relative p-4 rounded-2xl border border-stone-200/80 dark:border-zinc-800 bg-white/90 dark:bg-zinc-900/70 hover:border-indigo-400 dark:hover:border-indigo-500 hover:shadow-lg hover:shadow-indigo-500/10 transition-all duration-200 cursor-pointer flex flex-col justify-between"
          role="button"
          tabIndex={0}
        >
          <div className="flex items-start justify-between">
            <div className="w-11 h-11 rounded-xl bg-gradient-to-tr from-indigo-500 to-purple-400 text-white flex items-center justify-center shadow-md shadow-indigo-500/25 group-hover:scale-105 transition-transform">
              <PhoneCall className="w-5 h-5" />
            </div>
            <span className="text-[10px] uppercase font-bold tracking-wider px-2 py-0.5 rounded-full bg-indigo-500/10 text-indigo-600 dark:text-indigo-400 border border-indigo-500/20">
              Circle
            </span>
          </div>

          <div className="mt-4 space-y-1">
            <h4 className="text-sm font-bold text-stone-900 dark:text-zinc-100 group-hover:text-indigo-600 dark:group-hover:text-indigo-400 transition-colors">
              Family & Caregiver
            </h4>
            <p className="text-xs text-stone-500 dark:text-zinc-400 leading-snug truncate">
              {persona.emergencyContacts[0]?.name || "Caregiver Circle"}
            </p>
          </div>

          <div className="mt-3 pt-2.5 border-t border-stone-100 dark:border-zinc-800 flex items-center justify-between text-xs font-semibold text-indigo-600 dark:text-indigo-400">
            <span>Call or chime Echo</span>
            <span className="text-base group-hover:translate-x-0.5 transition-transform">&rarr;</span>
          </div>
        </div>
      </div>
    </div>
  )
}
