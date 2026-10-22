import React, { useState } from 'react'
import { useNavigate, useLocation, Link } from 'react-router-dom'
import { authApi } from '../services/endpoints'
import { apiErrorMessage } from '../services/api'
import { useAuth } from '../context/AuthContext.jsx'
import { formatAccountNumber } from '../utils/format'
import { Alert, CopyButton } from '../components/UI.jsx'

export default function Login() {
  const navigate = useNavigate()
  const location = useLocation()
  const { login } = useAuth()

  const [identifier, setIdentifier] = useState(location.state?.username || '')
  const [password, setPassword] = useState('')
  const [showPw, setShowPw] = useState(false)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const { justVerified, accountNumber, username } = location.state || {}

  const submit = async (e) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const { data } = await authApi.login({ identifier: identifier.trim(), password })
      login(data)
      if (!data.pin_set) navigate('/set-pin')
      else navigate(location.state?.from?.pathname || '/dashboard')
    } catch (err) {
      setError(apiErrorMessage(err))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="max-w-md mx-auto px-4 sm:px-6 py-10 sm:py-16">
      <h1 className="font-display text-3xl text-white mb-2">Welcome back</h1>
      <p className="text-slate-400 text-sm mb-6">Log in with your account number, username, email or phone number.</p>

      {justVerified && (
        <div className="zp-card p-4 mb-5 border-teal-500/40">
          <p className="text-teal-300 text-sm font-medium mb-1">Account verified — welcome aboard!</p>
          {accountNumber && (
            <>
              <p className="text-xs text-slate-400 mb-2">Your account number{username ? ` (username @${username})` : ''}:</p>
              <div className="flex items-center justify-between gap-3">
                <span className="zp-amount text-xl text-white tracking-wider">{formatAccountNumber(accountNumber)}</span>
                <CopyButton text={accountNumber} />
              </div>
            </>
          )}
        </div>
      )}
      <Alert type="error">{error}</Alert>

      <form onSubmit={submit} className="zp-card p-5 sm:p-6 space-y-4">
        <div>
          <label className="zp-label" htmlFor="identifier">Account number, username, email or phone</label>
          <input id="identifier" className="zp-input" required autoComplete="username" autoCapitalize="none" autoCorrect="off" spellCheck={false}
            value={identifier} onChange={(e) => setIdentifier(e.target.value)} placeholder="e.g. ada_lovelace or 7009255634" />
        </div>
        <div>
          <label className="zp-label" htmlFor="password">Password</label>
          <div className="relative">
            <input id="password" className="zp-input pr-16" type={showPw ? 'text' : 'password'} required autoComplete="current-password"
              value={password} onChange={(e) => setPassword(e.target.value)} placeholder="••••••••" />
            <button type="button" onClick={() => setShowPw((v) => !v)} className="absolute right-2 top-1/2 -translate-y-1/2 text-xs text-slate-400 hover:text-white px-2 py-2" aria-label={showPw ? 'Hide password' : 'Show password'}>
              {showPw ? 'Hide' : 'Show'}
            </button>
          </div>
        </div>
        <button type="submit" disabled={loading} className="zp-btn-primary w-full min-h-[48px]">
          {loading ? 'Logging in…' : 'Log in'}
        </button>
      </form>

      <p className="text-center text-sm text-slate-500 mt-6">
        New to ZionhiltPay? <Link to="/register" className="text-gold-400 hover:underline">Create an account</Link>
      </p>
    </div>
  )
}
