import React, { useState } from "react"
import { 
  X, 
  Phone, 
  Bell, 
  ShieldAlert, 
  UserCheck, 
  Heart,
  Check,
  Loader2
} from "lucide-react"
import { sound } from "@/services/sound"
import { PersonaProfile, EmergencyContact } from "@/types"

interface FamilyCircleModalProps {
  isOpen: boolean
  onClose: () => void
  persona: PersonaProfile
  onSendChime: () => Promise<void>
  onDispatchAlert: () => Promise<void>
}

export const FamilyCircleModal: React.FC<FamilyCircleModalProps> = ({
  isOpen,
  onClose,
  persona,
  onSendChime,
  onDispatchAlert,
}) => {
  const [loadingChime, setLoadingChime] = useState(false)
  const [loadingAlert, setLoadingAlert] = useState(false)
  const [chimeSuccess, setChimeSuccess] = useState(false)
  const [alertSuccess, setAlertSuccess] = useState(false)

  if (!isOpen) return null

  const handleChime = async () => {
    setLoadingChime(true)
    await onSendChime()
    setLoadingChime(false)
    setChimeSuccess(true)
    sound.playSuccessChime()
    setTimeout(() => setChimeSuccess(false), 2500)
  }

  const handleAlert = async () => {
    setLoadingAlert(true)
    await onDispatchAlert()
    setLoadingAlert(false)
    setAlertSuccess(true)
    sound.playAlertChime()
    setTimeout(() => setAlertSuccess(false), 2500)
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm animate-fade-in">
      <div className="relative w-full max-w-md rounded-3xl border border-stone-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 shadow-2xl p-6 space-y-5">
        {/* Header */}
        <div className="flex items-center justify-between pb-3 border-b border-stone-100 dark:border-zinc-800">
          <div className="flex items-center gap-2">
            <Heart className="w-5 h-5 text-rose-500" />
            <h3 className="font-bold text-base text-stone-900 dark:text-zinc-100">
              Family & Care Circle
            </h3>
          </div>
          <button
            onClick={onClose}
            className="p-1 rounded-lg text-stone-400 hover:text-stone-700 dark:hover:text-zinc-200"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Loved one reminder */}
        <div className="flex items-center gap-3 p-3 rounded-2xl bg-stone-50 dark:bg-zinc-800/50 border border-stone-100 dark:border-zinc-800">
          <img
            src={persona.photo}
            alt={persona.name}
            className="w-12 h-12 rounded-full object-cover border border-sky-400"
          />
          <div>
            <h4 className="font-bold text-sm text-stone-900 dark:text-zinc-100">
              {persona.name}
            </h4>
            <p className="text-xs text-stone-500 dark:text-zinc-400">
              {persona.location} · {persona.device}
            </p>
          </div>
        </div>

        {/* 1-Click Action Buttons */}
        <div className="space-y-2.5">
          <p className="text-xs uppercase tracking-wider font-bold text-stone-400">
            Immediate Actions
          </p>

          {/* Send gentle Echo chime */}
          <button
            onClick={handleChime}
            disabled={loadingChime}
            className="w-full flex items-center justify-between p-3.5 rounded-2xl border border-sky-200 dark:border-sky-900/60 bg-sky-50/70 dark:bg-sky-950/30 hover:bg-sky-100 dark:hover:bg-sky-900/40 text-stone-900 dark:text-zinc-100 transition-colors"
          >
            <div className="flex items-center gap-3 text-left">
              <div className="w-9 h-9 rounded-xl bg-sky-500 text-white flex items-center justify-center">
                {loadingChime ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : chimeSuccess ? (
                  <Check className="w-4 h-4" />
                ) : (
                  <Bell className="w-4 h-4" />
                )}
              </div>
              <div>
                <p className="text-xs font-bold">
                  {chimeSuccess ? "Gentle Chime Sent!" : "Send Gentle Alexa Chime"}
                </p>
                <p className="text-[11px] text-stone-500 dark:text-zinc-400">
                  Plays soft chime on {persona.device}
                </p>
              </div>
            </div>
            <span className="text-xs font-semibold text-sky-600 dark:text-sky-400">&rarr;</span>
          </button>

          {/* Dispatch SNS alert to caregiver */}
          <button
            onClick={handleAlert}
            disabled={loadingAlert}
            className="w-full flex items-center justify-between p-3.5 rounded-2xl border border-rose-200 dark:border-rose-900/60 bg-rose-50/70 dark:bg-rose-950/30 hover:bg-rose-100 dark:hover:bg-rose-900/40 text-stone-900 dark:text-zinc-100 transition-colors"
          >
            <div className="flex items-center gap-3 text-left">
              <div className="w-9 h-9 rounded-xl bg-rose-500 text-white flex items-center justify-center">
                {loadingAlert ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : alertSuccess ? (
                  <Check className="w-4 h-4" />
                ) : (
                  <ShieldAlert className="w-4 h-4" />
                )}
              </div>
              <div>
                <p className="text-xs font-bold">
                  {alertSuccess ? "Caregiver Alert Dispatched!" : "Alert Caregiver (Amazon SNS)"}
                </p>
                <p className="text-[11px] text-stone-500 dark:text-zinc-400">
                  Sends priority SMS alert to family circle
                </p>
              </div>
            </div>
            <span className="text-xs font-semibold text-rose-600 dark:text-rose-400">&rarr;</span>
          </button>
        </div>

        {/* Designated Contacts */}
        <div className="space-y-2">
          <p className="text-xs uppercase tracking-wider font-bold text-stone-400">
            Emergency Contacts
          </p>

          <div className="space-y-2">
            {persona.emergencyContacts.map((c: EmergencyContact, i: number) => (
              <div
                key={i}
                className="flex items-center justify-between p-3 rounded-xl bg-stone-50 dark:bg-zinc-800/40 border border-stone-200/60 dark:border-zinc-800 text-xs"
              >
                <div className="flex items-center gap-2.5">
                  <UserCheck className="w-4 h-4 text-emerald-500" />
                  <div>
                    <p className="font-bold text-stone-900 dark:text-zinc-100">{c.name}</p>
                    <p className="text-[11px] text-stone-500 dark:text-zinc-400">{c.relationship}</p>
                  </div>
                </div>

                <a
                  href={`tel:${c.phone}`}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white font-semibold transition-colors"
                >
                  <Phone className="w-3.5 h-3.5" />
                  <span>Call</span>
                </a>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
