// Gentle ambient Web Audio synthesis for Alexa+ and CareLoop interactions

class SoundManager {
  private ctx: AudioContext | null = null

  private getContext(): AudioContext | null {
    if (typeof window === "undefined") return null
    if (!this.ctx) {
      const AudioCtx = window.AudioContext || (window as any).webkitAudioContext
      if (AudioCtx) {
        this.ctx = new AudioCtx()
      }
    }
    if (this.ctx && this.ctx.state === "suspended") {
      this.ctx.resume().catch(() => {})
    }
    return this.ctx
  }

  // Play a soft, pleasant 2-tone Alexa chime (G5 -> C6)
  playAlexaChime() {
    try {
      const ctx = this.getContext()
      if (!ctx) return
      const now = ctx.currentTime

      const osc1 = ctx.createOscillator()
      const osc2 = ctx.createOscillator()
      const gain = ctx.createGain()

      gain.connect(ctx.destination)
      gain.gain.setValueAtTime(0.001, now)
      gain.gain.exponentialRampToValueAtTime(0.12, now + 0.04)
      gain.gain.exponentialRampToValueAtTime(0.001, now + 0.6)

      osc1.type = "sine"
      osc1.frequency.setValueAtTime(783.99, now) // G5
      osc1.frequency.setValueAtTime(1046.5, now + 0.16) // C6
      osc1.connect(gain)

      osc2.type = "triangle"
      osc2.frequency.setValueAtTime(392.0, now) // G4
      osc2.connect(gain)

      osc1.start(now)
      osc2.start(now)
      osc1.stop(now + 0.6)
      osc2.stop(now + 0.6)
    } catch {
      // Audio autoplay policy fallback
    }
  }

  // Play a warm confirmation chime when an action is completed (e.g. pills taken)
  playSuccessChime() {
    try {
      const ctx = this.getContext()
      if (!ctx) return
      const now = ctx.currentTime

      const freqs = [523.25, 659.25, 783.99] // C5, E5, G5 major triad
      freqs.forEach((freq, idx) => {
        const osc = ctx.createOscillator()
        const gain = ctx.createGain()
        const startTime = now + idx * 0.08

        gain.connect(ctx.destination)
        gain.gain.setValueAtTime(0.001, startTime)
        gain.gain.exponentialRampToValueAtTime(0.08, startTime + 0.03)
        gain.gain.exponentialRampToValueAtTime(0.001, startTime + 0.5)

        osc.type = "sine"
        osc.frequency.setValueAtTime(freq, startTime)
        osc.connect(gain)

        osc.start(startTime)
        osc.stop(startTime + 0.5)
      })
    } catch {
      // Audio autoplay policy fallback
    }
  }

  // Play a gentle alert ping for notifications
  playAlertChime() {
    try {
      const ctx = this.getContext()
      if (!ctx) return
      const now = ctx.currentTime

      const osc = ctx.createOscillator()
      const gain = ctx.createGain()

      gain.connect(ctx.destination)
      gain.gain.setValueAtTime(0.001, now)
      gain.gain.exponentialRampToValueAtTime(0.15, now + 0.02)
      gain.gain.exponentialRampToValueAtTime(0.001, now + 0.45)

      osc.type = "sine"
      osc.frequency.setValueAtTime(440, now)
      osc.frequency.setValueAtTime(370, now + 0.15)
      osc.connect(gain)

      osc.start(now)
      osc.stop(now + 0.45)
    } catch {
      // Audio autoplay policy fallback
    }
  }
}

export const sound = new SoundManager()
