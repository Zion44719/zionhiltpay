import React, { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { tierApi } from '../services/endpoints'
import { apiErrorMessage } from '../services/api'
import { Alert, Loader, ProgressBar } from '../components/UI.jsx'
import { formatNaira, formatDate } from '../utils/format'

function Meter({ label, value, max, text }) {
  return (
    <div>
      <div className="flex justify-between text-xs text-slate-400 mb-1.5 gap-3"><span>{label}</span><span className="text-right">{text}</span></div>
      <ProgressBar value={value} max={max} label={label} />
    </div>
  )
}

export default function AccountLevel() {
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    tierApi.overview().then(({ data: d }) => setData(d)).catch((e) => setError(apiErrorMessage(e))).finally(() => setLoading(false))
  }, [])

  if (loading) return <Loader />
  if (!data) return <div className="max-w-lg mx-auto px-4 py-10"><Alert type="error">{error || 'Could not load your account level.'}</Alert></div>

  const { usage, tiers, current_tier: cur, next_tier: next, request: req, last_rejection: rej } = data

  let cta = 'Upgrade my account'
  let note = next === 3 ? 'Submit a few documents to raise your limits.' : 'Submit a few documents to raise your limits. You can go straight from Tier 1 to Tier 3.'
  if (req?.status === 'draft') { cta = 'Continue my draft'; note = `You have a draft for Tier ${req.target_tier}, saved ${formatDate(req.updated_at)}.` }
  if (req?.status === 'pending') { cta = 'View or edit my documents'; note = `Your Tier ${req.target_tier} request is under review (submitted ${formatDate(req.submitted_at)}). You can still edit your documents.` }

  return (
    <div className="max-w-2xl mx-auto px-4 sm:px-6 py-6 sm:py-10">
      <Link to="/settings" className="text-sm text-slate-400 hover:text-white">← Settings</Link>
      <h1 className="font-display text-2xl sm:text-3xl text-white mt-2 mb-1">Account level</h1>
      <p className="text-slate-400 text-sm mb-6">Your level sets how much you can send each day and how much your wallet can hold.</p>
      <Alert type="error">{error}</Alert>

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
            {t.status === 'locked' && t.needs.length > 0 && (
              <ul className="mt-3 text-xs text-slate-400 space-y-1 list-disc pl-4">{t.needs.map((n) => <li key={n}>{n}</li>)}</ul>
            )}
          </div>
        ))}
      </div>

      {next ? (
        <section className="zp-card p-5" aria-label="Upgrade">
          <h2 className="font-display text-xl text-white mb-1">Move up a level</h2>
          {rej && !req && <Alert type="error">Your last request was not approved{rej.review_note ? `: ${rej.review_note}` : '.'} You can edit and submit again.</Alert>}
          <p className="text-sm text-slate-400 mb-4">{note}</p>
          <Link to="/settings/documents" className="zp-btn-primary w-full min-h-[48px]">{cta}</Link>
        </section>
      ) : (
        <p className="text-sm text-teal-300 text-center">You're on the highest level.</p>
      )}
    </div>
  )
}
