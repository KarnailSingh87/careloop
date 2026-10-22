import React from "react"
import { 
  Footprints, 
  Pill, 
  DoorOpen, 
  Coffee, 
  Moon, 
  CheckCircle2, 
  Clock, 
  Calendar 
} from "lucide-react"
import { RoutineItem } from "@/types"

interface RoutineScheduleProps {
  routines: RoutineItem[]
  onToggleRoutine: (id: string) => void
  personName: string
}

export const RoutineSchedule: React.FC<RoutineScheduleProps> = ({
  routines,
  onToggleRoutine,
  personName,
}) => {
  const getIcon = (category: string) => {
    switch (category) {
      case "medication":
        return <Pill className="w-4 h-4 text-sky-500" />
      case "door":
        return <DoorOpen className="w-4 h-4 text-emerald-500" />
      case "meal":
        return <Coffee className="w-4 h-4 text-amber-500" />
      case "checkin":
        return <Moon className="w-4 h-4 text-indigo-500" />
      default:
        return <Footprints className="w-4 h-4 text-teal-500" />
    }
  }

  const completedCount = routines.filter((r) => r.completed).length

  return (
    <div className="rounded-3xl border border-stone-200/90 dark:border-zinc-800 bg-white/70 dark:bg-zinc-900/60 backdrop-blur-xl shadow-lg p-5 sm:p-6 space-y-4">
      {/* Title & Count */}
      <div className="flex items-center justify-between pb-3 border-b border-stone-100 dark:border-zinc-800">
        <div className="flex items-center gap-2">
          <Calendar className="w-4 h-4 text-sky-500" />
          <h3 className="text-sm font-bold text-stone-900 dark:text-zinc-100">
            Today&apos;s Daily Routine Schedule
          </h3>
        </div>
        <span className="text-xs font-semibold px-2.5 py-0.5 rounded-full bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20">
          {completedCount} of {routines.length} Completed
        </span>
      </div>

      {/* Routine list */}
      <div className="space-y-3">
        {routines.map((routine) => {
          const isDone = routine.completed
          return (
            <div
              key={routine.id}
              onClick={() => onToggleRoutine(routine.id)}
              className={`p-3.5 rounded-2xl border transition-all duration-200 flex items-center justify-between gap-3 cursor-pointer ${
                isDone
                  ? "bg-stone-50/70 dark:bg-zinc-800/40 border-stone-200/60 dark:border-zinc-800 hover:border-emerald-300 dark:hover:border-emerald-800"
                  : "bg-white dark:bg-zinc-900/60 border-stone-200 dark:border-zinc-800 hover:border-sky-300 dark:hover:border-sky-700 shadow-sm"
              }`}
            >
              <div className="flex items-center gap-3 min-w-0">
                <div
                  className={`w-9 h-9 rounded-xl flex items-center justify-center flex-shrink-0 ${
                    isDone
                      ? "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400"
                      : "bg-stone-100 dark:bg-zinc-800 text-stone-600 dark:text-zinc-400"
                  }`}
                >
                  {getIcon(routine.category)}
                </div>

                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <p
                      className={`text-xs font-bold truncate ${
                        isDone
                          ? "text-stone-800 dark:text-zinc-200"
                          : "text-stone-900 dark:text-zinc-100"
                      }`}
                    >
                      {routine.title}
                    </p>
                    <span className="text-[10px] font-mono font-medium px-1.5 py-0.2 rounded bg-stone-100 dark:bg-zinc-800 text-stone-500 dark:text-zinc-400">
                      {routine.timeStr}
                    </span>
                  </div>
                  <p className="text-[11px] text-stone-500 dark:text-zinc-400 truncate">
                    {routine.sensor}
                  </p>
                </div>
              </div>

              {/* Status pill / Toggle */}
              <div className="flex items-center gap-2 flex-shrink-0">
                {isDone ? (
                  <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-[11px] font-semibold bg-emerald-50 dark:bg-emerald-950/40 text-emerald-700 dark:text-emerald-400 border border-emerald-200 dark:border-emerald-800/60">
                    <CheckCircle2 className="w-3.5 h-3.5" />
                    <span>Done ({routine.completedTime || "On time"})</span>
                  </span>
                ) : (
                  <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-[11px] font-semibold bg-stone-100 dark:bg-zinc-800 text-stone-600 dark:text-zinc-400 border border-stone-200 dark:border-zinc-700">
                    <Clock className="w-3.5 h-3.5" />
                    <span>Upcoming · Tap to mark</span>
                  </span>
                )}
              </div>
            </div>
          )
        })}
      </div>

      <div className="pt-2 flex items-center justify-between text-[11px] text-stone-400 dark:text-zinc-500">
        <span>Dynamic Circadian Grace: &plusmn;30m Circular EWMA</span>
        <span>Monitoring {personName}</span>
      </div>
    </div>
  )
}
