import React, { useState, useEffect } from "react"
import { CareLoopDemoCard } from "@/components/ui/demo"
import { ThemeToggle } from "@/components/ui/theme-toggle"
import { 
  ShieldCheck, 
  Activity, 
  Clock, 
  Bell, 
  Radio, 
  Sparkles, 
  HeartHandshake, 
  ExternalLink,
  Pill,
  Coffee,
  Footprints,
  DoorOpen
} from "lucide-react"

export default function App() {
  const [activePersona, setActivePersona] = useState<"dad" | "eleanor" | "martha">("dad")
  const [serverHealth, setServerHealth] = useState<{ status: string; clock_utc?: string } | null>(null)

  useEffect(() => {
    // Attempt health check on backend
    fetch("/health")
      .then((res) => res.json())
      .then((data) => setServerHealth(data))
      .catch(() => setServerHealth(null))
  }, [])

  const personas = [
    { id: "dad", name: "Arthur Davis (Dad)", age: 81, status: "Routines Normal", sub: "Retired Veteran · Living Independently" },
    { id: "eleanor", name: "Eleanor Davis (Mom)", age: 78, status: "Routines Normal", sub: "Structured Morning Schedule" },
    { id: "martha", name: "Martha Jenkins", age: 84, status: "Routines Normal", sub: "Late Riser · Gentle Reminders" },
  ]

  return (
    <div className="min-h-screen bg-[#f8f7f4] dark:bg-[#070b13] text-stone-900 dark:text-zinc-100 transition-colors duration-300">
      {/* Top Navigation */}
      <header className="border-b border-stone-200 dark:border-zinc-800/80 bg-white/70 dark:bg-zinc-900/60 backdrop-blur-md sticky top-0 z-50 px-4 sm:px-8 py-3.5">
        <div className="max-w-6xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl bg-gradient-to-tr from-sky-500 to-cyan-300 flex items-center justify-center shadow-md shadow-sky-500/20">
              <ShieldCheck className="w-5 h-5 text-white" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h1 className="font-bold text-lg tracking-tight bg-gradient-to-r from-stone-900 to-stone-600 dark:from-white dark:to-zinc-300 bg-clip-text text-transparent">
                  CareLoop
                </h1>
                <span className="text-[10px] font-semibold tracking-wider px-2 py-0.5 rounded-full bg-sky-500/10 text-sky-600 dark:text-sky-400 border border-sky-500/20">
                  ALEXA+ MCP
                </span>
              </div>
              <p className="text-xs text-stone-500 dark:text-zinc-400 hidden sm:block">
                Ambient Elder Care Safety & Circadian Routine Intelligence
              </p>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <a
              href="/simulator"
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-lg bg-sky-600 hover:bg-sky-500 text-white shadow-sm transition-all duration-200"
            >
              <span>Launch Simulator</span>
              <ExternalLink className="w-3.5 h-3.5" />
            </a>
            <ThemeToggle />
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-6xl mx-auto px-4 sm:px-8 py-8 space-y-8">
        {/* Hero Section */}
        <div className="text-center space-y-3 max-w-2xl mx-auto">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full text-xs font-medium bg-emerald-500/10 text-emerald-700 dark:text-emerald-400 border border-emerald-500/20">
            <Radio className="w-3.5 h-3.5 animate-pulse text-emerald-500" />
            <span>Deterministic Anomaly Safety · Zero LLM in Alert Logic</span>
          </div>
          <h2 className="text-3xl sm:text-4xl font-extrabold tracking-tight">
            Ambient Peace of Mind for Aging Loved Ones
          </h2>
          <p className="text-sm sm:text-base text-stone-600 dark:text-zinc-400">
            Learn circadian baseline rhythms with circular directional statistics. Alexa+ detects missed medications and prolonged immobility while protecting dignity without intrusive cameras.
          </p>
        </div>

        {/* Persona Selector Tabs */}
        <div className="flex justify-center">
          <div className="inline-flex p-1 rounded-xl bg-stone-200/80 dark:bg-zinc-800/80 border border-stone-300 dark:border-zinc-700">
            {personas.map((p) => (
              <button
                key={p.id}
                onClick={() => setActivePersona(p.id as any)}
                className={`px-4 py-2 rounded-lg text-xs font-medium transition-all duration-200 ${
                  activePersona === p.id
                    ? "bg-white dark:bg-zinc-900 text-sky-600 dark:text-sky-400 shadow-sm"
                    : "text-stone-600 dark:text-zinc-400 hover:text-stone-900 dark:hover:text-zinc-200"
                }`}
              >
                {p.name}
              </button>
            ))}
          </div>
        </div>

        {/* Core Showcase Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 items-start">
          {/* Ambient Preview Card */}
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-semibold text-stone-700 dark:text-zinc-300 flex items-center gap-2">
                <Sparkles className="w-4 h-4 text-amber-500" />
                <span>Ambient Preview Component</span>
              </h3>
              <span className="text-xs text-stone-500 dark:text-zinc-500">React + Tailwind UI</span>
            </div>
            <CareLoopDemoCard />

            <div className="p-4 rounded-xl border border-stone-200 dark:border-zinc-800 bg-white/50 dark:bg-zinc-900/40 text-xs space-y-2">
              <div className="flex items-center justify-between font-medium">
                <span className="text-stone-500 dark:text-zinc-400">Backend Server Status:</span>
                <span className="inline-flex items-center gap-1.5 text-emerald-600 dark:text-emerald-400">
                  <span className="w-2 h-2 rounded-full bg-emerald-500"></span>
                  {serverHealth ? "Streamable HTTP Live (/mcp)" : "MCP Server Standby"}
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-stone-500 dark:text-zinc-400">Circadian Learning Engine:</span>
                <span className="font-mono text-sky-600 dark:text-sky-400">Circular EWMA [0, 1440m)</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-stone-500 dark:text-zinc-400">Safety Invariant:</span>
                <span className="text-stone-700 dark:text-zinc-300 font-semibold">100% Deterministic (Zero-LLM Alerting)</span>
              </div>
            </div>
          </div>

          {/* Routine Baseline Timeline Card */}
          <div className="p-5 sm:p-6 rounded-2xl border bg-white dark:bg-zinc-900 border-stone-200 dark:border-zinc-800 shadow-lg space-y-5">
            <div className="flex items-center justify-between pb-3 border-b border-stone-100 dark:border-zinc-800">
              <div className="flex items-center gap-2">
                <Activity className="w-4 h-4 text-sky-500" />
                <span className="font-bold text-sm tracking-wide">
                  Learned Daily Routine Baselines
                </span>
              </div>
              <span className="text-xs font-mono text-stone-500 dark:text-zinc-400">
                Grace: &mu; + max(2&sigma;, 30m)
              </span>
            </div>

            <div className="space-y-3.5">
              <div className="flex items-center gap-3 p-2.5 rounded-xl bg-stone-50 dark:bg-zinc-800/40 border border-stone-100 dark:border-zinc-800">
                <div className="w-8 h-8 rounded-lg bg-amber-500/10 text-amber-600 dark:text-amber-400 flex items-center justify-center">
                  <Footprints className="w-4 h-4" />
                </div>
                <div className="flex-1">
                  <div className="flex justify-between items-center text-xs font-semibold">
                    <span>Morning Wake-up & Movement</span>
                    <span className="font-mono text-stone-500 dark:text-zinc-400">07:00 UTC (&plusmn;6m)</span>
                  </div>
                  <p className="text-[11px] text-stone-500 dark:text-zinc-400">Bedroom PIR Sensor</p>
                </div>
              </div>

              <div className="flex items-center gap-3 p-2.5 rounded-xl bg-stone-50 dark:bg-zinc-800/40 border border-stone-100 dark:border-zinc-800">
                <div className="w-8 h-8 rounded-lg bg-sky-500/10 text-sky-600 dark:text-sky-400 flex items-center justify-center">
                  <Pill className="w-4 h-4" />
                </div>
                <div className="flex-1">
                  <div className="flex justify-between items-center text-xs font-semibold">
                    <span>Prescription Heart Medication</span>
                    <span className="font-mono text-stone-500 dark:text-zinc-400">08:00 UTC (&plusmn;5m)</span>
                  </div>
                  <p className="text-[11px] text-stone-500 dark:text-zinc-400">Smart Pill Dispenser Tray 1</p>
                </div>
              </div>

              <div className="flex items-center gap-3 p-2.5 rounded-xl bg-stone-50 dark:bg-zinc-800/40 border border-stone-100 dark:border-zinc-800">
                <div className="w-8 h-8 rounded-lg bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 flex items-center justify-center">
                  <DoorOpen className="w-4 h-4" />
                </div>
                <div className="flex-1">
                  <div className="flex justify-between items-center text-xs font-semibold">
                    <span>Garden Check & Exterior Door</span>
                    <span className="font-mono text-stone-500 dark:text-zinc-400">11:15 UTC (&plusmn;8m)</span>
                  </div>
                  <p className="text-[11px] text-stone-500 dark:text-zinc-400">Patio Door Contact Sensor</p>
                </div>
              </div>

              <div className="flex items-center gap-3 p-2.5 rounded-xl bg-stone-50 dark:bg-zinc-800/40 border border-stone-100 dark:border-zinc-800">
                <div className="w-8 h-8 rounded-lg bg-orange-500/10 text-orange-600 dark:text-orange-400 flex items-center justify-center">
                  <Coffee className="w-4 h-4" />
                </div>
                <div className="flex-1">
                  <div className="flex justify-between items-center text-xs font-semibold">
                    <span>Midday Lunch & Hydration</span>
                    <span className="font-mono text-stone-500 dark:text-zinc-400">12:30 UTC (&plusmn;7m)</span>
                  </div>
                  <p className="text-[11px] text-stone-500 dark:text-zinc-400">Kitchen Activity / Refrigerator Sensor</p>
                </div>
              </div>
            </div>

            <div className="pt-2 flex justify-between items-center text-xs text-stone-500 dark:text-zinc-400">
              <span className="flex items-center gap-1.5">
                <HeartHandshake className="w-4 h-4 text-rose-500" />
                <span>3-Stage Gentle Escalation</span>
              </span>
              <a
                href="/simulator"
                className="text-sky-600 dark:text-sky-400 font-medium hover:underline inline-flex items-center gap-1"
              >
                <span>Interactive Cockpit</span>
                &rarr;
              </a>
            </div>
          </div>
        </div>
      </main>
    </div>
  )
}
