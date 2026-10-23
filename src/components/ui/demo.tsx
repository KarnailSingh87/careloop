import React from "react"
import { ThemeToggle } from "@/components/ui/theme-toggle"
import { ShieldCheck, HeartPulse, User } from "lucide-react"

function DefaultToggle() {
  return (
    <div className="space-y-2 text-center">
      <div className="flex justify-center">
        <ThemeToggle />
      </div>
    </div>
  )
}

/**
 * Mobile-compatible CareLoop Preview Card demonstrating
 * Unsplash stock assets with theme switching (Off-white vs Dark).
 */
function CareLoopDemoCard() {
  return (
    <div className="max-w-md mx-auto p-4 sm:p-6 rounded-2xl border transition-colors duration-300 bg-white dark:bg-zinc-900 border-stone-200 dark:border-zinc-800 shadow-lg">
      <div className="flex items-center justify-between pb-4 border-b border-stone-100 dark:border-zinc-800">
        <div className="flex items-center gap-2">
          <ShieldCheck className="w-5 h-5 text-sky-500" />
          <span className="font-bold text-sm tracking-wide text-stone-900 dark:text-zinc-100">
            CareLoop Ambient Status
          </span>
        </div>
        <ThemeToggle />
      </div>

      <div className="mt-4 flex items-center gap-4">
        <img
          src="/portraits/arthur.jpg"
          alt="Arthur Davis (Dad)"
          className="w-14 h-14 rounded-full object-cover border-2 border-sky-400 shadow-sm"
        />
        <div>
          <h3 className="font-semibold text-base text-stone-900 dark:text-zinc-100">
            Arthur Davis (Dad)
          </h3>
          <p className="text-xs text-stone-500 dark:text-zinc-400">
            Age 81 · Living Independently
          </p>
          <div className="mt-1 flex items-center gap-1.5 text-xs font-medium text-emerald-600 dark:text-emerald-400">
            <HeartPulse className="w-3.5 h-3.5" />
            <span>Routines Normal · Medication Taken 8:05 AM</span>
          </div>
        </div>
      </div>
    </div>
  )
}

export { DefaultToggle, CareLoopDemoCard }
