import React, { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { authApi } from '../services/endpoints'
import { apiErrorMessage } from '../services/api'
import { Alert } from '../components/UI.jsx'

export default function SetPin() {
  const navigate = useNavigate()
  const [pin, setPin] = useState('')
  const [confirmPin, setConfirmPin] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const submit = async (e) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      await authApi.setPin({ pin, confirm_pin: confirmPin })
      navigate('/dashboard')
    } catch (err) {
      setError(apiErrorMessage(err))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="max-w-md mx-auto px-4 sm:px-6 py-16">
      <h1 className="font-display text-3xl text-white mb-2">Set your transaction PIN</h1>
      <p className="text-slate-400 text-sm mb-8">
        A 4-6 digit PIN, separate from your password, used to authorize transfers and withdrawals.
      </p>

      <Alert type="error">{error}</Alert>

      <form onSubmit={submit} className="zp-card p-6 space-y-4">
        <div>
          <label className="zp-label">New PIN</label>
          <input
            className="zp-input text-center tracking-[0.5em] text-2xl font-mono"
            required
            maxLength={6}
            inputMode="numeric"
            type="password"
            value={pin}
            onChange={(e) => setPin(e.target.value.replace(/\D/g, ''))}
            placeholder="••••"
          />
        </div>
        <div>
          <label className="zp-label">Confirm PIN</label>
          <input
            className="zp-input text-center tracking-[0.5em] text-2xl font-mono"
            required
            maxLength={6}
            inputMode="numeric"
            type="password"
            value={confirmPin}
            onChange={(e) => setConfirmPin(e.target.value.replace(/\D/g, ''))}
            placeholder="••••"
          />
        </div>
        <button type="submit" disabled={loading || pin.length < 4 || confirmPin.length < 4} className="zp-btn-primary w-full">
          {loading ? 'Saving…' : 'Set PIN and continue'}
        </button>
      </form>
    </div>
  )
}
