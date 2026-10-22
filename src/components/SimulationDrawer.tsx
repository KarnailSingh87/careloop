import React, { useState } from "react"
import { 
  X, 
  FastForward, 
  RotateCcw, 
  Clock, 
  Sparkles, 
  AlertTriangle,
  Database,
  CheckCircle,
  Loader2
} from "lucide-react"

interface SimulationDrawerProps {
  isOpen: boolean
  onClose: () => void
  onAdvanceClock: (minutes: number) => Promise<void>
  onSetTime: (time: string) => Promise<void>
  onResetClock: () => Promise<void>
  onTriggerScenario: (type: "skips_lunch" | "missed_meds") => Promise<void>
  onResetDemoData: () => Promise<void>
  clockUtc: string
  isBackendConnected: boolean
}

export const SimulationDrawer: React.FC<SimulationDrawerProps> = ({
  isOpen,
  onClose,
  onAdvanceClock,
  onSetTime,
  onResetClock,
  onTriggerScenario,
  onResetDemoData,
  clockUtc,
  isBackendConnected,
}) => {
  const [loading, setLoading] = useState(false)
  const [statusMsg, setStatusMsg] = useState<string | null>(null)

  if (!isOpen) return null

  const wrapAction = async (fn: () => Promise<void>, msg: string) => {
    setLoading(true)
    try {
      await fn()
      setStatusMsg(msg)
      setTimeout(() => setStatusMsg(null), 3000)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm animate-fade-in">
      <div className="relative w-full max-w-lg rounded-3xl border border-stone-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 shadow-2xl p-6 space-y-5 max-h-[90vh] overflow-y-auto">
        {/* Header */}
        <div className="flex items-center justify-between pb-3 border-b border-stone-100 dark:border-zinc-800">
          <div className="flex items-center gap-2">
            <Sparkles className="w-5 h-5 text-amber-500" />
            <h3 className="font-bold text-base text-stone-900 dark:text-zinc-100">
              Simulation & Testing Laboratory
            </h3>
          </div>
          <button
            onClick={onClose}
            className="p-1 rounded-lg text-stone-400 hover:text-stone-700 dark:hover:text-zinc-200"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {statusMsg && (
          <div className="p-3 rounded-xl bg-emerald-50 dark:bg-emerald-950/40 border border-emerald-200 dark:border-emerald-800 text-xs font-semibold text-emerald-700 dark:text-emerald-400 flex items-center gap-2">
            <CheckCircle className="w-4 h-4 flex-shrink-0" />
            <span>{statusMsg}</span>
          </div>
        )}

        {/* Current Clock */}
        <div className="flex items-center justify-between p-3.5 rounded-2xl bg-stone-50 dark:bg-zinc-800/50 border border-stone-200/60 dark:border-zinc-800">
          <div className="flex items-center gap-2.5">
            <Clock className="w-4 h-4 text-sky-500" />
            <div>
              <p className="text-xs font-bold text-stone-900 dark:text-zinc-100">
                Simulated Clock Engine
              </p>
              <p className="text-[11px] font-mono text-stone-500 dark:text-zinc-400">
                {clockUtc}
              </p>
            </div>
          </div>

          <span
            className={`text-[10px] font-bold px-2 py-0.5 rounded-full border ${
              isBackendConnected
                ? "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/20"
                : "bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/20"
            }`}
          >
            {isBackendConnected ? "Live FastMCP Synced" : "Local Engine"}
          </span>
        </div>

        {/* Clock Controls */}
        <div className="space-y-2">
          <p className="text-xs uppercase tracking-wider font-bold text-stone-400">
            Time Progression Controls
          </p>

          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
            <button
              onClick={() => wrapAction(() => onAdvanceClock(60), "Clock advanced by +1 Hour")}
              disabled={loading}
              className="p-2.5 rounded-xl border border-stone-200 dark:border-zinc-700 bg-stone-50 dark:bg-zinc-800 hover:bg-stone-100 dark:hover:bg-zinc-700 text-xs font-semibold text-stone-800 dark:text-zinc-200 flex flex-col items-center gap-1 transition-colors"
            >
              <FastForward className="w-4 h-4 text-sky-500" />
              <span>+1 Hour</span>
            </button>

            <button
              onClick={() => wrapAction(() => onAdvanceClock(240), "Clock advanced by +4 Hours")}
              disabled={loading}
              className="p-2.5 rounded-xl border border-stone-200 dark:border-zinc-700 bg-stone-50 dark:bg-zinc-800 hover:bg-stone-100 dark:hover:bg-zinc-700 text-xs font-semibold text-stone-800 dark:text-zinc-200 flex flex-col items-center gap-1 transition-colors"
            >
              <FastForward className="w-4 h-4 text-indigo-500" />
              <span>+4 Hours</span>
            </button>

            <button
              onClick={() => wrapAction(() => onSetTime("14:00"), "Simulated clock jumped to 2:00 PM (14:00)")}
              disabled={loading}
              className="p-2.5 rounded-xl border border-stone-200 dark:border-zinc-700 bg-stone-50 dark:bg-zinc-800 hover:bg-stone-100 dark:hover:bg-zinc-700 text-xs font-semibold text-stone-800 dark:text-zinc-200 flex flex-col items-center gap-1 transition-colors"
            >
              <Clock className="w-4 h-4 text-amber-500" />
              <span>Jump to 2 PM</span>
            </button>

            <button
              onClick={() => wrapAction(onResetClock, "Simulation clock reset to 08:15 AM")}
              disabled={loading}
              className="p-2.5 rounded-xl border border-stone-200 dark:border-zinc-700 bg-stone-50 dark:bg-zinc-800 hover:bg-stone-100 dark:hover:bg-zinc-700 text-xs font-semibold text-stone-800 dark:text-zinc-200 flex flex-col items-center gap-1 transition-colors"
            >
              <RotateCcw className="w-4 h-4 text-rose-500" />
              <span>Reset 8:15 AM</span>
            </button>
          </div>
        </div>

        {/* Hero Scenarios */}
        <div className="space-y-2">
          <p className="text-xs uppercase tracking-wider font-bold text-stone-400">
            Automated Evaluation Scenarios
          </p>

          <div className="space-y-2">
            {/* Scenario 1: Dad Skips Lunch */}
            <div
              onClick={() =>
                wrapAction(
                  () => onTriggerScenario("skips_lunch"),
                  "Scenario 'Dad Skips Lunch' loaded! Clock at 14:00, stage escalated."
                )
              }
              className="p-3 rounded-2xl border border-amber-200 dark:border-amber-900/60 bg-amber-50/60 dark:bg-amber-950/20 hover:bg-amber-100/70 dark:hover:bg-amber-900/40 cursor-pointer transition-colors flex items-center justify-between"
              role="button"
              tabIndex={0}
            >
              <div className="space-y-0.5">
                <p className="text-xs font-bold text-stone-900 dark:text-zinc-100 flex items-center gap-1.5">
                  <AlertTriangle className="w-3.5 h-3.5 text-amber-500" />
                  <span>Dad Skips Lunch (Anomaly Escalation)</span>
                </p>
                <p className="text-[11px] text-stone-500 dark:text-zinc-400">
                  Simulates Arthur missing 12:30 lunch; triggers gentle check-in escalation
                </p>
              </div>
              <span className="text-xs font-bold text-amber-600 dark:text-amber-400">&rarr;</span>
            </div>

            {/* Scenario 2: Missed Morning Medication */}
            <div
              onClick={() =>
                wrapAction(
                  () => onTriggerScenario("missed_meds"),
                  "Scenario 'Missed Heart Medication' loaded! Alert active."
                )
              }
              className="p-3 rounded-2xl border border-rose-200 dark:border-rose-900/60 bg-rose-50/60 dark:bg-rose-950/20 hover:bg-rose-100/70 dark:hover:bg-rose-900/40 cursor-pointer transition-colors flex items-center justify-between"
              role="button"
              tabIndex={0}
            >
              <div className="space-y-0.5">
                <p className="text-xs font-bold text-stone-900 dark:text-zinc-100 flex items-center gap-1.5">
                  <AlertTriangle className="w-3.5 h-3.5 text-rose-500" />
                  <span>Missed Morning Heart Medication</span>
                </p>
                <p className="text-[11px] text-stone-500 dark:text-zinc-400">
                  Simulates 08:00 AM Metoprolol skipped past defensive grace window
                </p>
              </div>
              <span className="text-xs font-bold text-rose-600 dark:text-rose-400">&rarr;</span>
            </div>
          </div>
        </div>

        {/* Database & Reset */}
        <div className="pt-2 border-t border-stone-100 dark:border-zinc-800 flex items-center justify-between">
          <div className="flex items-center gap-2 text-[11px] text-stone-500 dark:text-zinc-400">
            <Database className="w-3.5 h-3.5" />
            <span>Isolated Demo Data Boundary</span>
          </div>

          <button
            onClick={() => wrapAction(onResetDemoData, "Demo data successfully wiped and reset to baseline.")}
            disabled={loading}
            className="px-3 py-1.5 rounded-lg border border-stone-200 dark:border-zinc-700 bg-stone-100 dark:bg-zinc-800 hover:bg-stone-200 dark:hover:bg-zinc-700 text-stone-700 dark:text-zinc-300 text-xs font-medium transition-colors flex items-center gap-1"
          >
            {loading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <RotateCcw className="w-3.5 h-3.5" />}
            <span>Reset Demo Data</span>
          </button>
        </div>
      </div>
    </div>
  )
}
