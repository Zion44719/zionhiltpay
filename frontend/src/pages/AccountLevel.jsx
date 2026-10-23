import React, { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { tierApi } from '../services/endpoints'
import { apiErrorMessage } from '../services/api'
import { useAuth } from '../context/AuthContext.jsx'
import { Alert, Loader, ProgressBar } from '../components/UI.jsx'
import { formatNaira, formatDate } from '../utils/format'

const MAX_DOC = 6_000_000

function Meter({ label, value, max, text }) {
  return (
    <div>
      <div className="flex justify-between text-xs text-slate-400 mb-1.5 gap-3"><span>{label}</span><span className="text-right">{text}</span></div>
      <ProgressBar value={value} max={max} label={label} />
    </div>
  )
}

function Requirement({ r }) {
  return (
    <li className="flex items-start gap-2.5 text-sm">
      <span className={`mt-0.5 ${r.done ? 'text-teal-300' : 'text-slate-500'}`} aria-hidden="true">{r.done ? '✓' : '○'}</span>
      <span className={r.done ? 'text-slate-300' : 'text-slate-400'}>
        {r.label}{r.detail && !r.done ? <span className="text-gold-400"> ({r.detail})</span> : null}
        {r.key === 'photo' && !r.done && <> {' '}<Link to="/profile" className="text-gold-400 hover:underline">Add one</Link></>}
      </span>
    </li>
  )
}

export default function AccountLevel() {
  const { refreshProfile } = useAuth()
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const [ok, setOk] = useState('')
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [bvn, setBvn] = useState('')
  const [address, setAddress] = useState('')
  const [doc, setDoc] = useState(null)
  const [preview, setPreview] = useState(null)
  const fileRef = useRef(null)

  const load = async () => {
    try { const { data: d } = await tierApi.overview(); setData(d) } catch (e) { setError(apiErrorMessage(e)) } finally { setLoading(false) }
  }
  useEffect(() => { load() }, [])
  useEffect(() => () => { if (preview) URL.revokeObjectURL(preview) }, [preview])

  if (loading) return <Loader />
  if (!data) return <div className="max-w-lg mx-auto px-4 py-10"><Alert type="error">{error || 'Could not load your account level.'}</Alert></div>

  const { usage, tiers, current_tier: cur, next_tier: next, pending_request: pending, last_rejection: rej } = data
  const nextTier = tiers.find((t) => t.tier === next)
  const unmet = nextTier ? nextTier.requirements.filter((r) => !r.done && !r.at_request) : []

  const pickDoc = (e) => {
    const f = e.target.files?.[0]; e.target.value = ''
    setError('')
    if (!f) return
    if (!f.type.startsWith('image/')) return setError('Please attach a photo of the document (JPEG, PNG or WebP). PDFs are not accepted.')
    if (f.size > MAX_DOC) return setError('That photo is too large. Please choose one under 6 MB.')
    setDoc(f); setPreview(URL.createObjectURL(f))
  }

  const submit = async (e) => {
    e.preventDefault()
    setError(''); setOk('')
    const form = new FormData()
    form.append('target_tier', String(next))
    if (next === 2) {
      if (!/^\d{11}$/.test(bvn)) return setError('Your BVN is exactly 11 digits.')
      form.append('bvn', bvn)
    } else {
      if (address.trim().length < 15) return setError('Enter your full residential address (street, area, city and state).')
      if (!doc) return setError('Attach a photo of a utility bill or other proof of address.')
      form.append('address', address.trim()); form.append('document', doc)
    }
    setBusy(true)
    try {
      await tierApi.upgrade(form)
      setOk(`Request sent. We'll review it and update your account level.`)
      setBvn(''); setAddress(''); setDoc(null); setPreview(null)
      await load(); await refreshProfile()
    } catch (err) { setError(apiErrorMessage(err)) } finally { setBusy(false) }
  }

  return (
    <div className="max-w-2xl mx-auto px-4 sm:px-6 py-6 sm:py-10">
      <Link to="/settings" className="text-sm text-slate-400 hover:text-white">← Settings</Link>
      <h1 className="font-display text-2xl sm:text-3xl text-white mt-2 mb-1">Account level</h1>
      <p className="text-slate-400 text-sm mb-6">Your level sets how much you can send each day and how much your wallet can hold.</p>
      <Alert type="error">{error}</Alert>
      <Alert type="success">{ok}</Alert>

      <section className="zp-card p-5 mb-6" aria-label="Your limits today">
        <div className="flex items-center justify-between mb-4">
          <span className="zp-pill text-gold-400 border-gold-500/40 bg-gold-500/10">Tier {cur}</span>
          <span className="text-xs text-slate-500">Resets at midnight (Lagos time)</span>
        </div>
        <div className="space-y-4">
          {usage.daily_limit != null
            ? <Meter label="Sent today" value={usage.spent_today} max={usage.daily_limit} text={`${formatNaira(usage.spent_today)} of ${formatNaira(usage.daily_limit)}`} />
            : <p className="text-sm text-slate-300">No daily limit on this tier.</p>}
          {usage.max_balance != null
            ? <Meter label="Wallet balance" value={usage.balance} max={usage.max_balance} text={`${formatNaira(usage.balance)} of ${formatNaira(usage.max_balance)} allowed`} />
            : <p className="text-sm text-slate-300">No limit on your wallet balance.</p>}
        </div>
      </section>

      <div className="space-y-3 mb-6">
        {tiers.map((t) => (
          <div key={t.tier} className={`zp-card p-4 ${t.status === 'current' ? 'border-gold-500/50' : ''}`}>
            <div className="flex items-center justify-between gap-3 mb-2">
              <h2 className="font-display text-lg text-white">Tier {t.tier}</h2>
              {t.status === 'current' && <span className="zp-pill text-gold-400 border-gold-500/40 bg-gold-500/10">Your level</span>}
              {t.status === 'done' && <span className="zp-pill text-teal-300 border-teal-500/40 bg-teal-500/10">Unlocked</span>}
            </div>
            <p className="text-sm text-slate-300">Send up to <strong className="zp-amount">{t.daily_limit != null ? formatNaira(t.daily_limit) : 'any amount'}</strong> a day</p>
            <p className="text-sm text-slate-300">{t.max_balance != null ? <>Hold up to <strong className="zp-amount">{formatNaira(t.max_balance)}</strong></> : 'No limit on how much you hold'}</p>
          </div>
        ))}
      </div>

      {next && (
        <section className="zp-card p-5" aria-label={`Upgrade to Tier ${next}`}>
          <h2 className="font-display text-xl text-white mb-1">Upgrade to Tier {next}</h2>
          {pending ? (
            <p className="text-sm text-gold-400 mt-2">Your Tier {pending.target_tier} request was sent on {formatDate(pending.created_at)} and is being reviewed. We'll update your level when it's approved.</p>
          ) : (
            <>
              {rej && <Alert type="error">Your last request was not approved{rej.review_note ? `: ${rej.review_note}` : '.'} You can try again below.</Alert>}
              <ul className="space-y-2 my-4">{nextTier.requirements.map((r) => <Requirement key={r.key} r={r} />)}</ul>
              {unmet.length > 0 ? (
                <p className="text-sm text-slate-400">Complete the steps above, then come back to send your request.</p>
              ) : (
                <form onSubmit={submit} className="space-y-4">
                  {next === 2 ? (
                    <div>
                      <label className="zp-label" htmlFor="bvn">Bank Verification Number (BVN)</label>
                      <input id="bvn" className="zp-input font-mono tracking-wider" inputMode="numeric" autoComplete="off" maxLength={11}
                        value={bvn} onChange={(e) => setBvn(e.target.value.replace(/\D/g, ''))} placeholder="11 digits" />
                      <p className="text-xs text-slate-500 mt-1.5">Dial *565*0# on the phone number linked to your bank to see yours. We store it encrypted.</p>
                    </div>
                  ) : (
                    <>
                      <div>
                        <label className="zp-label" htmlFor="address">Residential address</label>
                        <textarea id="address" className="zp-input" rows={3} maxLength={300} value={address} onChange={(e) => setAddress(e.target.value)} placeholder="House number, street, area, city, state" />
                      </div>
                      <div>
                        <span className="zp-label">Proof of address (photo)</span>
                        <input ref={fileRef} type="file" accept="image/jpeg,image/png,image/webp" className="sr-only" onChange={pickDoc} aria-label="Choose a proof of address photo" />
                        <button type="button" onClick={() => fileRef.current?.click()} className="zp-btn-secondary w-full min-h-[48px]">{doc ? 'Choose a different photo' : 'Take or choose a photo'}</button>
                        <p className="text-xs text-slate-500 mt-1.5">A utility bill or similar, dated within 3 months. Make sure the name and address are readable.</p>
                        {preview && <img src={preview} alt="Preview of your document" className="mt-3 rounded-lg border border-ink-600 max-h-56 mx-auto" />}
                      </div>
                    </>
                  )}
                  <button type="submit" disabled={busy} className="zp-btn-primary w-full min-h-[48px]">{busy ? 'Sending…' : `Request Tier ${next}`}</button>
                </form>
              )}
            </>
          )}
        </section>
      )}
      {!next && <p className="text-sm text-teal-300 text-center">You're on the highest level.</p>}
    </div>
  )
}
