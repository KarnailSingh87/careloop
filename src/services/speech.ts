// Web Speech API text-to-speech engine for realistic Alexa+ voice responses

class SpeechService {
  private enabled: boolean = true

  constructor() {
    if (typeof window !== "undefined") {
      const stored = localStorage.getItem("careloop_speech_enabled")
      this.enabled = stored !== null ? stored === "true" : true
    }
  }

  isEnabled(): boolean {
    return this.enabled
  }

  setEnabled(val: boolean) {
    this.enabled = val
    if (typeof window !== "undefined") {
      localStorage.setItem("careloop_speech_enabled", String(val))
    }
    if (!val && typeof window !== "undefined" && window.speechSynthesis) {
      window.speechSynthesis.cancel()
    }
  }

  speak(text: string, onEnd?: () => void) {
    if (!this.enabled || typeof window === "undefined" || !("speechSynthesis" in window)) {
      if (onEnd) onEnd()
      return
    }

    try {
      window.speechSynthesis.cancel()

      // Clean SSML tags if any exist in the response
      const cleanText = text.replace(/<[^>]*>/g, "").trim()
      if (!cleanText) return

      const utterance = new SpeechSynthesisUtterance(cleanText)
      utterance.rate = 1.02
      utterance.pitch = 1.05

      // Try selecting an English natural voice (Samantha, Victoria, Google US English, etc.)
      const voices = window.speechSynthesis.getVoices()
      const preferred = voices.find(
        (v) =>
          v.lang.startsWith("en") &&
          (v.name.includes("Samantha") ||
            v.name.includes("Karen") ||
            v.name.includes("Natural") ||
            v.name.includes("Female") ||
            v.name.includes("Google US English"))
      ) || voices.find((v) => v.lang.startsWith("en"))

      if (preferred) {
        utterance.voice = preferred
      }

      if (onEnd) {
        utterance.onend = () => onEnd()
        utterance.onerror = () => onEnd()
      }

      window.speechSynthesis.speak(utterance)
    } catch {
      if (onEnd) onEnd()
    }
  }

  stop() {
    if (typeof window !== "undefined" && "speechSynthesis" in window) {
      window.speechSynthesis.cancel()
    }
  }
}

export const speech = new SpeechService()
