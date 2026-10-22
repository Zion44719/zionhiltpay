import React, { useEffect, useRef, useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { authApi } from '../services/endpoints'
import { apiErrorMessage } from '../services/api'
import { normalizePhone } from '../utils/format'
import { Alert } from '../components/UI.jsx'

const USERNAME_RE = /^[a-z][a-z0-9_]{2,19}$/
const ID_TYPES = [
  { value: 'national_id', label: 'National ID (NIN)', hint: '11 digits' },
  { value: 'drivers_license', label: "Driver's license", hint: '8–20 letters/digits' },
]

function validateId(type, raw) {
  const s = raw.replace(/[\s\-/]/g, '').toUpperCase()
  if (type === 'national_id') return /^\d{11}$/.test(s) && new Set(s).size > 1 ? '' : 'A National ID (NIN) is exactly 11 digits.'
  return /^[A-Z0-9]{8,20}$/.test(s) && /\d/.test(s) ? '' : "A driver's license number is 8–20 letters/digits and includes a digit."
}

function Rule({ ok, children }) {
  return (
    <li className={`flex items-center gap-2 text-xs ${ok ? 'text-teal-300' : 'text-slate-500'}`}>
      <span aria-hidden="true">{ok ? '✓' : '○'}</span>{children}
    </li>
  )
}

export default function Register() {
  const navigate = useNavigate()
  const [step, setStep] = useState(1)
  const [form, setForm] = useState({
    full_name: '', username: '', email: '', phone_number: '', password: '',
    preferred_otp_channel: 'email', id_type: 'national_id', id_number: '', consent: false,
  })
  const [showPw, setShowPw] = useState(false)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [uname, setUname] = useState({ state: 'idle', msg: '' })
  const seq = useRef(0)

  const update = (key) => (e) => setForm({ ...form, [key]: e.target.value })
  const phone = normalizePhone(form.phone_number)
  const pw = form.password
  const pwOk = { len: pw.length >= 8, up: /[A-Z]/.test(pw), low: /[a-z]/.test(pw), dig: /\d/.test(pw) }
  const unameLower = form.username.trim().toLowerCase()

  // live username availability (debounced; stale responses ignored)
  useEffect(() => {
    if (!unameLower) { setUname({ state: 'idle', msg: '' }); return }
    if (!USERNAME_RE.test(unameLower)) {
      setUname({ state: 'bad', msg: '3–20 characters, start with a letter; letters, digits and _ only.' }); return
    }
    setUname({ state: 'checking', msg: 'Checking…' })
    const mine = ++seq.current
    const t = setTimeout(async () => {
      try {
        const { data } = await authApi.usernameAvailable(unameLower)
        if (mine !== seq.current) return
        setUname(data.available ? { state: 'ok', msg: 'Available' } : { state: 'bad', msg: data.reason || 'Not available' })
      } catch {
        if (mine === seq.current) setUname({ state: 'idle', msg: '' })
      }
    }, 450)
    return () => clearTimeout(t)
  }, [unameLower])

  const step1Error = () => {
    if (form.full_name.trim().length < 2) return 'Please enter your full name.'
    if (!USERNAME_RE.test(unameLower)) return 'Choose a valid username.'
    if (uname.state === 'bad') return uname.msg
    if (!/^\S+@\S+\.\S+$/.test(form.email)) return 'Enter a valid email address.'
    if (!phone) return 'Enter a valid phone number, e.g. 08012345678 or +2348012345678.'
    if (!(pwOk.len && pwOk.up && pwOk.low && pwOk.dig)) return 'Your password does not meet all the rules yet.'
    return ''
  }

  const next = (e) => {
    e.preventDefault()
    const problem = step1Error()
    setError(problem)
    if (!problem) { setStep(2); window.scrollTo({ top: 0 }) }
  }

  const submit = async (e) => {
    e.preventDefault()
    setError('')
    const idProblem = validateId(form.id_type, form.id_number)
    if (idProblem) return setError(idProblem)
    if (!form.consent) return setError('Please tick the box to consent to identity verification.')
    setLoading(true)
    try {
      const { data } = await authApi.register({
        full_name: form.full_name, username: unameLower, email: form.email, phone_number: form.phone_number,
        password: form.password, preferred_otp_channel: form.preferred_otp_channel,
        id_type: form.id_type, id_number: form.id_number, consent_id_processing: form.consent,
      })
      navigate('/verify-otp', {
        state: {
          email: data.email, phone_number: data.phone_number, purpose: 'registration', channel: data.otp_channel,
          username: data.username, accountNumber: data.account_number,
        },
      })
    } catch (err) {
      const msg = apiErrorMessage(err)
      setError(msg)
      if (/username|email|phone/i.test(msg) && !/ID/.test(msg)) setStep(1)   // problem is on the first page
    } finally {
      setLoading(false)
    }
  }

  const idMeta = ID_TYPES.find((t) => t.value === form.id_type)

  return (
    <div className="max-w-md mx-auto px-4 sm:px-6 py-10 sm:py-16">
      <p className="text-xs uppercase tracking-wider text-gold-400 mb-2">Step {step} of 2 · {step === 1 ? 'Your account' : 'Verify your identity'}</p>
      <div className="flex gap-2 mb-5" aria-hidden="true">
        <div className="h-1 flex-1 rounded-full bg-gold-500" />
        <div className={`h-1 flex-1 rounded-full ${step === 2 ? 'bg-gold-500' : 'bg-ink-600'}`} />
      </div>
      <h1 className="font-display text-3xl text-white mb-2">{step === 1 ? 'Create your wallet' : 'Confirm who you are'}</h1>
      <p className="text-slate-400 text-sm mb-6">
        {step === 1
          ? 'Takes about two minutes. You get a unique account number the moment you sign up.'
          : 'Financial regulations require us to know our customers. Your ID is encrypted and only used for identity verification.'}
      </p>

      <Alert type="error">{error}</Alert>

      {step === 1 && (
        <form onSubmit={next} className="zp-card p-5 sm:p-6 space-y-4" noValidate>
          <div>
            <label className="zp-label" htmlFor="full_name">Full name (as on your ID)</label>
            <input id="full_name" className="zp-input" autoComplete="name" value={form.full_name} onChange={update('full_name')} placeholder="Ada Lovelace" />
          </div>
          <div>
            <label className="zp-label" htmlFor="username">Username</label>
            <input id="username" className="zp-input" autoComplete="username" autoCapitalize="none" autoCorrect="off" spellCheck={false}
              value={form.username} onChange={update('username')} placeholder="ada_lovelace" />
            {uname.msg && (
              <p className={`text-xs mt-1.5 ${uname.state === 'ok' ? 'text-teal-300' : uname.state === 'bad' ? 'text-red-300' : 'text-slate-500'}`}>
                {uname.state === 'ok' ? '✓ ' : ''}{uname.msg}
              </p>
            )}
          </div>
          <div>
            <label className="zp-label" htmlFor="email">Email</label>
            <input id="email" className="zp-input" type="email" inputMode="email" autoComplete="email" autoCapitalize="none" value={form.email} onChange={update('email')} placeholder="you@example.com" />
          </div>
          <div>
            <label className="zp-label" htmlFor="phone">Phone number</label>
            <input id="phone" className="zp-input" type="tel" inputMode="tel" autoComplete="tel" value={form.phone_number} onChange={update('phone_number')} placeholder="08012345678" />
            {form.phone_number && (
              <p className={`text-xs mt-1.5 ${phone ? 'text-teal-300' : 'text-slate-500'}`}>
                {phone ? `✓ We'll use ${phone}` : 'Use 08012345678 or +2348012345678 (other countries: start with + and the country code)'}
              </p>
            )}
          </div>
          <div>
            <label className="zp-label" htmlFor="password">Password</label>
            <div className="relative">
              <input id="password" className="zp-input pr-16" type={showPw ? 'text' : 'password'} autoComplete="new-password" value={form.password} onChange={update('password')} placeholder="Create a strong password" />
              <button type="button" onClick={() => setShowPw((v) => !v)} className="absolute right-2 top-1/2 -translate-y-1/2 text-xs text-slate-400 hover:text-white px-2 py-2" aria-label={showPw ? 'Hide password' : 'Show password'}>
                {showPw ? 'Hide' : 'Show'}
              </button>
            </div>
            <ul className="grid grid-cols-2 gap-x-3 gap-y-1 mt-2">
              <Rule ok={pwOk.len}>8+ characters</Rule>
              <Rule ok={pwOk.up}>Uppercase letter</Rule>
              <Rule ok={pwOk.low}>Lowercase letter</Rule>
              <Rule ok={pwOk.dig}>A digit</Rule>
            </ul>
          </div>
          <div>
            <p className="zp-label">Send my verification code by</p>
            <div className="grid grid-cols-2 gap-3">
              {['email', 'sms'].map((ch) => (
                <button type="button" key={ch} onClick={() => setForm({ ...form, preferred_otp_channel: ch })}
                  aria-pressed={form.preferred_otp_channel === ch}
                  className={`rounded-lg px-4 py-3 min-h-[48px] text-sm font-medium border transition-colors ${
                    form.preferred_otp_channel === ch ? 'border-gold-500 bg-gold-500/10 text-gold-400' : 'border-ink-600 text-slate-400 hover:border-ink-500'}`}>
                  {ch === 'email' ? 'Email' : 'SMS'}
                </button>
              ))}
            </div>
          </div>
          <button type="submit" className="zp-btn-primary w-full min-h-[48px] mt-2">Continue</button>
        </form>
      )}

      {step === 2 && (
        <form onSubmit={submit} className="zp-card p-5 sm:p-6 space-y-4" noValidate>
          <div>
            <p className="zp-label">Which ID will you use?</p>
            <div className="grid grid-cols-2 gap-3">
              {ID_TYPES.map((t) => (
                <button type="button" key={t.value} aria-pressed={form.id_type === t.value}
                  onClick={() => setForm({ ...form, id_type: t.value, id_number: '' })}
                  className={`rounded-lg px-3 py-3 min-h-[64px] text-left border transition-colors ${
                    form.id_type === t.value ? 'border-gold-500 bg-gold-500/10' : 'border-ink-600 hover:border-ink-500'}`}>
                  <span className={`block text-sm font-medium ${form.id_type === t.value ? 'text-gold-400' : 'text-slate-200'}`}>{t.label}</span>
                  <span className="block text-xs text-slate-500 mt-0.5">{t.hint}</span>
                </button>
              ))}
            </div>
          </div>
          <div>
            <label className="zp-label" htmlFor="id_number">{idMeta.label} number</label>
            <input id="id_number" className="zp-input font-mono tracking-wider" autoComplete="off" autoCapitalize="characters" spellCheck={false}
              inputMode={form.id_type === 'national_id' ? 'numeric' : 'text'}
              maxLength={form.id_type === 'national_id' ? 11 : 24}
              value={form.id_number}
              onChange={(e) => setForm({ ...form, id_number: form.id_type === 'national_id' ? e.target.value.replace(/\D/g, '') : e.target.value.toUpperCase() })}
              placeholder={form.id_type === 'national_id' ? '12345678901' : 'ABC12345AA01'} />
          </div>
          <label className="flex items-start gap-3 text-sm text-slate-300 cursor-pointer">
            <input type="checkbox" className="mt-1 w-5 h-5 accent-[#DDAA4E] shrink-0" checked={form.consent} onChange={(e) => setForm({ ...form, consent: e.target.checked })} />
            <span>I consent to ZionhiltPay processing my ID number to verify my identity. It is stored encrypted and never shown in full.</span>
          </label>
          <div className="flex gap-3 pt-1">
            <button type="button" onClick={() => { setStep(1); setError('') }} className="zp-btn-secondary min-h-[48px] px-5">Back</button>
            <button type="submit" disabled={loading} className="zp-btn-primary flex-1 min-h-[48px]">{loading ? 'Creating account…' : 'Create account'}</button>
          </div>
        </form>
      )}

      <p className="text-center text-sm text-slate-500 mt-6">
        Already have an account? <Link to="/login" className="text-gold-400 hover:underline">Log in</Link>
      </p>
    </div>
  )
}
