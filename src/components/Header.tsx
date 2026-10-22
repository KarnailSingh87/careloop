import React from "react"
import { ShieldCheck, Volume2, VolumeX, Sparkles } from "lucide-react"
import { ThemeToggle } from "@/components/ui/theme-toggle"
import { PERSONA_PROFILES } from "@/services/api"
import { PersonaProfile } from "@/types"

interface HeaderProps {
  activePersonaId: string
  onSelectPersona: (id: "dad" | "eleanor" | "martha") => void
  isConnected: boolean
  displayTime: string
  speechEnabled: boolean
  onToggleSpeech: () => void
  onOpenTestingLab: () => void
}

export const Header: React.FC<HeaderProps> = ({
  activePersonaId,
  onSelectPersona,
  isConnected,
  displayTime,
  speechEnabled,
  onToggleSpeech,
  onOpenTestingLab,
}) => {
  const personas: PersonaProfile[] = Object.values(PERSONA_PROFILES)

  return (
    <header className="border-b border-stone-200/80 dark:border-zinc-800/80 bg-white/80 dark:bg-zinc-900/80 backdrop-blur-md sticky top-0 z-40 transition-colors duration-200">
      <div className="max-w-6xl mx-auto px-4 sm:px-6 py-3 flex items-center justify-between gap-4">
        {/* Brand identity */}
        <div className="flex items-center gap-3">
          <div className="relative flex items-center justify-center w-10 h-10 rounded-xl bg-gradient-to-br from-sky-500 to-teal-400 text-white shadow-md shadow-sky-500/20">
            <ShieldCheck className="w-6 h-6" />
            <span className="absolute -bottom-0.5 -right-0.5 w-3 h-3 rounded-full bg-emerald-500 border-2 border-white dark:border-zinc-900 animate-pulse" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="font-extrabold text-lg sm:text-xl tracking-tight text-stone-900 dark:text-zinc-100">
                CareLoop
              </h1>
              <span className="text-[10px] uppercase font-bold tracking-wider px-2 py-0.5 rounded-full bg-sky-500/10 text-sky-600 dark:text-sky-400 border border-sky-500/20">
                Alexa+ Ambient
              </span>
            </div>
            <p className="text-xs text-stone-500 dark:text-zinc-400 hidden sm:block">
              Elder Care Safety & Circadian Peace of Mind
            </p>
          </div>
        </div>

        {/* Persona quick switch buttons */}
        <div className="hidden md:flex items-center p-1 rounded-xl bg-stone-100 dark:bg-zinc-800/70 border border-stone-200 dark:border-zinc-700/60">
          {personas.map((p) => {
            const isActive = activePersonaId === p.id
            return (
              <button
                key={p.id}
                onClick={() => onSelectPersona(p.id)}
                className={`flex items-center gap-2 px-3.5 py-1.5 rounded-lg text-xs font-semibold transition-all duration-200 ${
                  isActive
                    ? "bg-white dark:bg-zinc-900 text-sky-600 dark:text-sky-400 shadow-sm"
                    : "text-stone-600 dark:text-zinc-400 hover:text-stone-900 dark:hover:text-zinc-200"
                }`}
              >
                <img
                  src={p.photo}
                  alt={p.name}
                  className="w-5 h-5 rounded-full object-cover border border-sky-400/40"
                />
                <span>{p.shortName}</span>
                <span className="text-[10px] opacity-70 font-normal">({p.age})</span>
              </button>
            )
          })}
        </div>

        {/* Right side controls */}
        <div className="flex items-center gap-2 sm:gap-3">
          {/* Status & Clock pill */}
          <div className="flex items-center gap-2 px-2.5 py-1.5 rounded-lg bg-stone-100 dark:bg-zinc-800/60 border border-stone-200 dark:border-zinc-700/60 text-xs font-medium">
            <span
              className={`w-2 h-2 rounded-full ${
                isConnected ? "bg-emerald-500 shadow-sm shadow-emerald-500/50" : "bg-amber-500 animate-pulse"
              }`}
            />
            <span className="font-mono text-stone-700 dark:text-zinc-300">
              {displayTime}
            </span>
          </div>

          {/* Voice Speech toggle */}
          <button
            onClick={onToggleSpeech}
            title={speechEnabled ? "Voice speech enabled (click to mute)" : "Voice speech muted (click to enable)"}
            className={`p-2 rounded-lg border text-xs transition-colors duration-150 ${
              speechEnabled
                ? "bg-sky-50 dark:bg-sky-950/40 border-sky-200 dark:border-sky-800 text-sky-600 dark:text-sky-400"
                : "bg-stone-100 dark:bg-zinc-800 border-stone-200 dark:border-zinc-700 text-stone-400"
            }`}
            aria-label="Toggle speech audio"
          >
            {speechEnabled ? <Volume2 className="w-4 h-4" /> : <VolumeX className="w-4 h-4" />}
          </button>

          {/* Testing Lab Drawer Trigger */}
          <button
            onClick={onOpenTestingLab}
            className="hidden sm:inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-lg bg-stone-100 dark:bg-zinc-800 hover:bg-stone-200 dark:hover:bg-zinc-700 text-stone-700 dark:text-zinc-300 border border-stone-200 dark:border-zinc-700 transition-colors"
          >
            <Sparkles className="w-3.5 h-3.5 text-amber-500" />
            <span>Simulate</span>
          </button>

          {/* Theme switcher */}
          <ThemeToggle />
        </div>
      </div>

      {/* Mobile persona switcher bar */}
      <div className="md:hidden flex items-center justify-around border-t border-stone-200 dark:border-zinc-800 bg-stone-50/50 dark:bg-zinc-900/50 px-2 py-2">
        {personas.map((p) => {
          const isActive = activePersonaId === p.id
          return (
            <button
              key={p.id}
              onClick={() => onSelectPersona(p.id)}
              className={`flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium transition-all ${
                isActive
                  ? "bg-sky-500 text-white font-semibold shadow-sm"
                  : "text-stone-600 dark:text-zinc-400"
              }`}
            >
              <img src={p.photo} alt={p.name} className="w-4 h-4 rounded-full object-cover" />
              <span>{p.shortName}</span>
            </button>
          )
        })}
      </div>
    </header>
  )
}
