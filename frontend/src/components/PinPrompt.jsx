import React, { useState } from 'react'

export default function PinPrompt({ open, onCancel, onConfirm, loading, error }) {
  const [pin, setPin] = useState('')

  if (!open) return null

  const submit = (e) => {
    e.preventDefault()
    onConfirm(pin)
  }

  return (
    <div className="fixed inset-0 bg-black/70 backdrop-blur-sm z-50 flex items-center justify-center px-4">
      <div className="zp-card w-full max-w-sm p-6">
        <h3 className="font-display text-xl text-white mb-1">Confirm with your PIN</h3>
        <p className="text-sm text-slate-400 mb-5">Enter your transaction PIN to authorize this action.</p>
        {error && <p className="text-sm text-red-300 mb-3">{error}</p>}
        <form onSubmit={submit}>
          <input
            autoFocus
            className="zp-input text-center tracking-[0.5em] text-2xl font-mono mb-4"
            maxLength={6}
            inputMode="numeric"
            type="password"
            value={pin}
            onChange={(e) => setPin(e.target.value.replace(/\D/g, ''))}
            placeholder="••••"
          />
          <div className="flex gap-3">
            <button type="button" onClick={onCancel} className="zp-btn-secondary flex-1">Cancel</button>
            <button type="submit" disabled={loading || pin.length < 4} className="zp-btn-primary flex-1">
              {loading ? 'Confirming…' : 'Confirm'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
