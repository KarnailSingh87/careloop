import React, { useState, useRef, useEffect } from "react"
import { 
  Radio, 
  Send, 
  Mic, 
  MicOff, 
  Sparkles, 
  Volume2, 
  RotateCcw,
  Loader2
} from "lucide-react"
import { sound } from "@/services/sound"
import { speech } from "@/services/speech"
import { PersonaProfile } from "@/types"

export interface MessageItem {
  id: string
  sender: "user" | "alexa"
  text: string
  timeStr: string
}

interface AlexaConsoleProps {
  persona: PersonaProfile
  messages: MessageItem[]
  onSendMessage: (text: string) => Promise<void>
  isProcessing: boolean
  onClearHistory: () => void
}

export const AlexaConsole: React.FC<AlexaConsoleProps> = ({
  persona,
  messages,
  onSendMessage,
  isProcessing,
  onClearHistory,
}) => {
  const [inputText, setInputText] = useState("")
  const [isListening, setIsListening] = useState(false)
  const messagesEndRef = useRef<HTMLDivElement>(null)

  // Scroll to bottom when new messages arrive
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [messages, isProcessing])

  // Suggested prompt chips tailored to persona
  const promptChips = [
    `"Did ${persona.shortName} take pills today?"`,
    `"Check ${persona.shortName}'s routine health"`,
    `"Give me today's daily summary"`,
    `"What time did ${persona.shortName} eat lunch?"`,
  ]

  const handleSubmit = async (e?: React.FormEvent) => {
    if (e) e.preventDefault()
    const trimmed = inputText.trim()
    if (!trimmed || isProcessing) return

    setInputText("")
    sound.playAlexaChime()
    await onSendMessage(trimmed)
  }

  const handleChipClick = async (chip: string) => {
    if (isProcessing) return
    const cleanPrompt = chip.replace(/^"|"$/g, "")
    sound.playAlexaChime()
    await onSendMessage(cleanPrompt)
  }

  // Web Speech recognition toggle
  const toggleSpeechRecognition = () => {
    const SpeechRec = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition
    if (!SpeechRec) {
      alert("Speech recognition is not supported in this browser. Please type your query in the box below.")
      return
    }

    if (isListening) {
      setIsListening(false)
      return
    }

    try {
      const recognition = new SpeechRec()
      recognition.lang = "en-US"
      recognition.interimResults = false
      recognition.maxAlternatives = 1

      recognition.onstart = () => {
        setIsListening(true)
        sound.playAlexaChime()
      }

      recognition.onresult = (event: any) => {
        const transcript = event.results[0][0].transcript
        setIsListening(false)
        if (transcript) {
          setInputText(transcript)
          onSendMessage(transcript)
        }
      }

      recognition.onerror = () => {
        setIsListening(false)
      }

      recognition.onend = () => {
        setIsListening(false)
      }

      recognition.start()
    } catch {
      setIsListening(false)
    }
  }

  return (
    <div className="rounded-3xl border border-stone-200/90 dark:border-zinc-800 bg-white/70 dark:bg-zinc-900/60 backdrop-blur-xl shadow-lg p-5 sm:p-6 flex flex-col justify-between space-y-4">
      {/* Alexa Header */}
      <div className="flex items-center justify-between pb-3 border-b border-stone-100 dark:border-zinc-800">
        <div className="flex items-center gap-3">
          {/* Pulsing Alexa Ring / Orb */}
          <div className="relative flex items-center justify-center">
            <div
              className={`w-9 h-9 rounded-full bg-gradient-to-tr from-cyan-400 via-sky-500 to-indigo-600 shadow-lg shadow-sky-500/30 flex items-center justify-center transition-transform ${
                isProcessing || isListening ? "scale-110 animate-pulse" : ""
              }`}
            >
              <Radio className="w-4 h-4 text-white" />
            </div>
            {(isProcessing || isListening) && (
              <span className="absolute -inset-1 rounded-full border border-sky-400 animate-ping opacity-60" />
            )}
          </div>

          <div>
            <div className="flex items-center gap-2">
              <h3 className="text-sm font-bold text-stone-900 dark:text-zinc-100">
                Alexa+ Ambient Companion
              </h3>
              <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-cyan-500/10 text-cyan-700 dark:text-cyan-400 border border-cyan-500/20">
                {isListening ? "Listening..." : isProcessing ? "Thinking..." : "Ready"}
              </span>
            </div>
            <p className="text-[11px] text-stone-500 dark:text-zinc-400">
              Synced with {persona.device} · Voice & Factual Q&A
            </p>
          </div>
        </div>

        <button
          onClick={onClearHistory}
          className="p-1.5 rounded-lg text-stone-400 hover:text-stone-600 dark:hover:text-zinc-300 transition-colors"
          title="Clear conversation history"
        >
          <RotateCcw className="w-3.5 h-3.5" />
        </button>
      </div>

      {/* Suggested quick chips */}
      <div className="flex items-center gap-2 overflow-x-auto pb-1 scrollbar-none text-xs">
        <span className="text-stone-400 flex items-center gap-1 flex-shrink-0 text-[11px]">
          <Sparkles className="w-3 h-3 text-amber-500" />
          <span>Quick:</span>
        </span>
        {promptChips.map((chip, idx) => (
          <button
            key={idx}
            onClick={() => handleChipClick(chip)}
            disabled={isProcessing}
            className="flex-shrink-0 px-2.5 py-1 rounded-full bg-stone-100 dark:bg-zinc-800/80 hover:bg-sky-50 dark:hover:bg-sky-950/40 text-stone-700 dark:text-zinc-300 hover:text-sky-600 dark:hover:text-sky-400 border border-stone-200/80 dark:border-zinc-700 text-xs font-medium transition-colors"
          >
            {chip}
          </button>
        ))}
      </div>

      {/* Conversation speech bubble thread */}
      <div className="max-h-60 min-h-[140px] overflow-y-auto space-y-3 pr-1 text-xs">
        {messages.map((m) => {
          const isUser = m.sender === "user"
          return (
            <div
              key={m.id}
              className={`flex flex-col ${isUser ? "items-end" : "items-start"}`}
            >
              <div className="flex items-center gap-1.5 mb-1 px-1 text-[10px] text-stone-400">
                <span>{isUser ? "Caregiver" : "Alexa+ Echo"}</span>
                <span>&bull;</span>
                <span>{m.timeStr}</span>
              </div>
              <div
                className={`max-w-[85%] rounded-2xl px-4 py-2.5 leading-relaxed shadow-sm ${
                  isUser
                    ? "bg-sky-600 text-white rounded-br-none"
                    : "bg-stone-100 dark:bg-zinc-800 text-stone-800 dark:text-zinc-200 rounded-bl-none border border-stone-200/60 dark:border-zinc-700/60"
                }`}
              >
                {!isUser && (
                  <button
                    onClick={() => speech.speak(m.text)}
                    className="inline-flex items-center gap-1 text-[11px] text-sky-600 dark:text-sky-400 hover:underline mb-1 mr-2"
                    title="Play voice audio"
                  >
                    <Volume2 className="w-3 h-3 inline" />
                  </button>
                )}
                <span>{m.text}</span>
              </div>
            </div>
          )
        })}

        {isProcessing && (
          <div className="flex items-center gap-2 text-stone-500 dark:text-zinc-400 p-2">
            <Loader2 className="w-4 h-4 animate-spin text-sky-500" />
            <span className="text-xs">Alexa+ is consulting memory & sensors...</span>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input bar */}
      <form onSubmit={handleSubmit} className="relative flex items-center gap-2">
        <div className="relative flex-1">
          <input
            type="text"
            value={inputText}
            onChange={(e) => setInputText(e.target.value)}
            placeholder={`Ask Alexa+ about ${persona.shortName}...`}
            disabled={isProcessing}
            className="w-full pl-3.5 pr-10 py-2.5 text-xs rounded-xl bg-stone-100 dark:bg-zinc-800/80 border border-stone-200 dark:border-zinc-700 text-stone-900 dark:text-zinc-100 placeholder-stone-400 focus:outline-none focus:ring-2 focus:ring-sky-500/40 transition-all"
          />
          <button
            type="button"
            onClick={toggleSpeechRecognition}
            className={`absolute right-2 top-1/2 -translate-y-1/2 p-1.5 rounded-lg transition-colors ${
              isListening
                ? "text-red-500 animate-pulse bg-red-100 dark:bg-red-950/50"
                : "text-stone-400 hover:text-stone-600 dark:hover:text-zinc-200"
            }`}
            title="Toggle speech dictation"
          >
            {isListening ? <MicOff className="w-4 h-4" /> : <Mic className="w-4 h-4" />}
          </button>
        </div>

        <button
          type="submit"
          disabled={!inputText.trim() || isProcessing}
          className="px-4 py-2.5 rounded-xl bg-sky-600 hover:bg-sky-500 disabled:opacity-40 text-white font-semibold text-xs shadow-sm flex items-center gap-1.5 transition-colors"
        >
          <span>Ask</span>
          <Send className="w-3 h-3" />
        </button>
      </form>
    </div>
  )
}
