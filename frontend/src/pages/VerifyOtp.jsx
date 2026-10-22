import React, { useState, useEffect, useRef } from 'react'
import { useNavigate, useLocation, Link } from 'react-router-dom'
import { authApi } from '../services/endpoints'
import { apiErrorMessage } from '../services/api'
import { Alert } from '../components/UI.jsx'

export default function VerifyOtp() {
  const navigate = useNavigate()
  const location = useLocation()
  const { email, phone_number, purpose = 'registration', channel = 'email', username, accountNumber } = location.state || {}

  const [code, setCode] = useState('')
  const [error, setError] = useState('')
  const [info, setInfo] = useState('')
  const [loading, setLoading] = useState(false)
  const [cooldown, setCooldown] = useState(0)
  const timerRef = useRef(null)

  useEffect(() => {
    if (!email && !phone_number) {
      navigate('/register')
    }
  }, [email, phone_number, navigate])

  useEffect(() => {
    if (cooldown <= 0) return
    timerRef.current = setTimeout(() => setCooldown((c) => c - 1), 1000)
    return () => clearTimeout(timerRef.current)
  }, [cooldown])

  const submit = async (e) => {
    e.preventDefault()
    setError('')
    setInfo('')
    setLoading(true)
    try {
      await authApi.verifyOtp({ ...(channel === 'sms' ? { phone_number } : { email }), purpose, code })
      navigate('/login', { state: { justVerified: true, username, accountNumber } })
    } catch (err) {
      setError(apiErrorMessage(err))
    } finally {
      setLoading(false)
    }
  }

  const resend = async () => {
    setError('')
    setInfo('')
    try {
      await authApi.resendOtp({ email, phone_number, purpose, channel })
      setInfo(`A new code has been sent via ${channel}.`)
      setCooldown(60)
    } catch (err) {
      setError(apiErrorMessage(err))
    }
  }

  return (
    <div className="max-w-md mx-auto px-4 sm:px-6 py-16">
      <h1 className="font-display text-3xl text-white mb-2">Verify your account</h1>
      <p className="text-slate-400 text-sm mb-8">
        We sent a {String(channel).toUpperCase()} code to {channel === 'email' ? email : phone_number}. It expires in 10 minutes.
      </p>

      <Alert type="error">{error}</Alert>
      <Alert type="success">{info}</Alert>

      <form onSubmit={submit} className="zp-card p-6 space-y-4">
        <div>
          <label className="zp-label">6-digit code</label>
          <input
            className="zp-input text-center tracking-[0.5em] text-2xl font-mono"
            required
            maxLength={6}
            inputMode="numeric"
            value={code}
            onChange={(e) => setCode(e.target.value.replace(/\D/g, ''))}
            placeholder="000000"
          />
        </div>
        <button type="submit" disabled={loading || code.length !== 6} className="zp-btn-primary w-full">
          {loading ? 'Verifying…' : 'Verify'}
        </button>
        <button
          type="button"
          onClick={resend}
          disabled={cooldown > 0}
          className="zp-btn-ghost w-full text-sm"
        >
          {cooldown > 0 ? `Resend code in ${cooldown}s` : 'Resend code'}
        </button>
      </form>

      <p className="text-center text-sm text-slate-500 mt-6">
        Wrong details? <Link to="/register" className="text-gold-400 hover:underline">Start over</Link>
      </p>
    </div>
  )
}
