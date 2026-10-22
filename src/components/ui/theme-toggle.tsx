"use client"

import { useEffect, useState } from "react"
import { Moon, Sun } from "lucide-react"
import { cn } from "@/lib/utils"

interface ThemeToggleProps {
  className?: string
  onChange?: (isDark: boolean) => void
}

export function ThemeToggle({ className, onChange }: ThemeToggleProps) {
  const [isDark, setIsDark] = useState(true)

  // Initialize theme from document or localStorage
  useEffect(() => {
    if (typeof window !== "undefined") {
      const stored = localStorage.getItem("careloop_theme")
      const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches
      const initialDark = stored ? stored === "dark" : prefersDark
      setIsDark(initialDark)
      applyTheme(initialDark)
    }
  }, [])

  const applyTheme = (dark: boolean) => {
    if (typeof document !== "undefined") {
      const root = document.documentElement
      if (dark) {
        root.classList.add("dark")
        root.classList.remove("light")
        root.setAttribute("data-theme", "dark")
      } else {
        root.classList.remove("dark")
        root.classList.add("light")
        root.setAttribute("data-theme", "off-white")
      }
      localStorage.setItem("careloop_theme", dark ? "dark" : "off-white")
    }
  }

  const handleToggle = () => {
    const next = !isDark
    setIsDark(next)
    applyTheme(next)
    if (onChange) onChange(next)
  }

  return (
    <div
      className={cn(
        "flex w-16 h-8 p-1 rounded-full cursor-pointer transition-all duration-300 select-none shadow-sm",
        isDark 
          ? "bg-zinc-950 border border-zinc-800" 
          : "bg-offwhite-100 border border-offwhite-300",
        className
      )}
      onClick={handleToggle}
      role="button"
      tabIndex={0}
      aria-label={isDark ? "Switch to off-white theme" : "Switch to dark theme"}
    >
      <div className="flex justify-between items-center w-full">
        <div
          className={cn(
            "flex justify-center items-center w-6 h-6 rounded-full transition-transform duration-300 shadow-sm",
            isDark 
              ? "transform translate-x-0 bg-zinc-800" 
              : "transform translate-x-8 bg-white border border-stone-200"
          )}
        >
          {isDark ? (
            <Moon 
              className="w-4 h-4 text-white" 
              strokeWidth={1.5}
            />
          ) : (
            <Sun 
              className="w-4 h-4 text-amber-600" 
              strokeWidth={1.5}
            />
          )}
        </div>
        <div
          className={cn(
            "flex justify-center items-center w-6 h-6 rounded-full transition-transform duration-300",
            isDark 
              ? "bg-transparent" 
              : "transform -translate-x-8"
          )}
        >
          {isDark ? (
            <Sun 
              className="w-4 h-4 text-gray-500" 
              strokeWidth={1.5}
            />
          ) : (
            <Moon 
              className="w-4 h-4 text-stone-400" 
              strokeWidth={1.5}
            />
          )}
        </div>
      </div>
    </div>
  )
}
