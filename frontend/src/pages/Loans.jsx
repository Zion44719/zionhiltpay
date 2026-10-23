import React, { useCallback, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { loanApi } from '../services/endpoints'
import { apiErrorMessage } from '../services/api'
import { Alert, Loader, ProgressBar } from '../components/UI.jsx'
import PinPrompt from '../components/PinPrompt.jsx'
import { formatNaira, formatDate } from '../utils/format'

export default function Loans() {
  const [offer, setOffer] = useState(null)
  const [loans, setLoans] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [ok, setOk] = useState('')
  const [amount, setAmount] = useState('')
  const [days, setDays] = useState(null)
  const [quote, setQuote] = useState(null)
  const [quoteErr, setQuoteErr] = useState('')
  const [accept, setAccept] = useState(false)
  const [pin, setPin] = useState({ open: false, mode: null, loan: null, amount: 0, loading: false, error: '' })
  const [repay, setRepay] = useState('')
  const seq = useRef(0)

  const load = useCallback(async () => {
    try {
      const [o, l] = await Promise.all([loanApi.offer(), loanApi.list()])
      setOffer(o.data); setLoans(l.data)
      setDays((d) => d ?? o.data.tenors?.[0]?.days ?? null)
    } catch (e) { setError(apiErrorMessage(e)) } finally { setLoading(false) }
  }, [])
  useEffect(() => { load() }, [load])

  // live quote: the person always sees exactly what they will owe before agreeing
  useEffect(() => {
    setQuote(null); setQuoteErr('')
    const a = Number(amount)
    if (!offer?.eligible || !a || !days) return undefined
    const mine = ++seq.current
    const t = setTimeout(async () => {
      try { const { data } = await loanApi.quote(a, days); if (mine === seq.current) setQuote(data) }
      catch (e) { if (mine === seq.current) setQuoteErr(apiErrorMessage(e)) }
    }, 400)
    return () => clearTimeout(t)
  }, [amount, days, offer])

  if (loading) return <Loader />
  const active = offer?.active_loan

  const confirm = async (value) => {
    setPin((p) => ({ ...p, loading: true, error: '' }))
    try {
      if (pin.mode === 'apply') {
        const { data } = await loanApi.apply({ amount: Number(amount), tenor_days: days, pin: value, accept_terms: true })
        setOk(`Done! ${formatNaira(data.principal)} is now in your wallet. Repay ${formatNaira(data.total_due)} by ${formatDate(data.due_at)}.`)
        setAmount(''); setAccept(false)
      } else {
        const { data } = await loanApi.repay(pin.loan.id, pin.amount, value)
        setOk(data.status === 'repaid' ? 'Loan fully repaid. Thank you!' : `Payment received. You still owe ${formatNaira(data.outstanding)}.`)
        setRepay('')
      }
      setPin({ open: false, mode: null, loan: null, amount: 0, loading: false, error: '' })
      setError(''); await load()
    } catch (e) { setPin((p) => ({ ...p, loading: false, error: apiErrorMessage(e) })) }
  }

  return (
    <div className="max-w-xl mx-auto px-4 sm:px-6 py-6 sm:py-10">
      <Link to="/settings" className="text-sm text-slate-400 hover:text-white">← Settings</Link>
      <h1 className="font-display text-2xl sm:text-3xl text-white mt-2 mb-1">Loans</h1>
      <p className="text-slate-400 text-sm mb-6">Borrow what you need, see the exact cost first, and repay early any time.</p>
      <Alert type="error">{error}</Alert>
      <Alert type="success">{ok}</Alert>

      {active && (
        <section className="zp-card p-5 mb-6" aria-label="Your current loan">
          <div className="flex items-center justify-between gap-3 mb-3">
            <h2 className="font-display text-lg text-white">Current loan</h2>
            {active.is_overdue
              ? <span className="zp-pill text-red-300 border-red-500/40 bg-red-500/10">Overdue</span>
              : <span className="zp-pill text-gold-400 border-gold-500/40 bg-gold-500/10">Active</span>}
          </div>
          <p className="zp-amount text-3xl text-gold-400 mb-1">{formatNaira(active.outstanding)}</p>
          <p className="text-xs text-slate-400 mb-4">still to repay · due {formatDate(active.due_at)}</p>
          <ProgressBar value={active.repaid} max={active.total_due} label="Repaid" danger={active.is_overdue} />
          <p className="text-xs text-slate-500 mt-2">{formatNaira(active.repaid)} of {formatNaira(active.total_due)} repaid (borrowed {formatNaira(active.principal)} + {formatNaira(active.interest)} interest)</p>
          <div className="mt-4 space-y-3">
            <label className="zp-label" htmlFor="repay">Amount to repay (₦)</label>
            <input id="repay" className="zp-input zp-amount" type="number" inputMode="decimal" min="1" step="0.01" max={active.outstanding} value={repay} onChange={(e) => setRepay(e.target.value)} placeholder="0.00" />
            <div className="grid grid-cols-2 gap-3">
              <button type="button" className="zp-btn-secondary min-h-[48px]" onClick={() => setRepay(String(active.outstanding))}>Pay in full</button>
              <button type="button" disabled={!(Number(repay) > 0)} className="zp-btn-primary min-h-[48px]" onClick={() => setPin({ open: true, mode: 'repay', loan: active, amount: Number(repay), loading: false, error: '' })}>Repay</button>
            </div>
          </div>
        </section>
      )}

      {!active && offer && (
        <section className="zp-card p-5 mb-6" aria-label="Get a loan">
          {!offer.eligible ? (
            <>
              <h2 className="font-display text-lg text-white mb-2">Loans aren't available to you yet</h2>
              {offer.reasons.map((r) => <p key={r} className="text-sm text-slate-300 mb-1">{r}</p>)}
              {offer.tier < 2 && <Link to="/settings/level" className="zp-btn-primary mt-4 min-h-[48px] w-full">Upgrade my account level</Link>}
            </>
          ) : (
            <>
              <h2 className="font-display text-lg text-white mb-1">Get a loan</h2>
              <p className="text-xs text-slate-400 mb-4">You can borrow {formatNaira(offer.min_amount)} to {formatNaira(offer.max_amount)} right now.</p>
              <label className="zp-label" htmlFor="loan-amount">How much? (₦)</label>
              <input id="loan-amount" className="zp-input zp-amount" type="number" inputMode="decimal" min={offer.min_amount} max={offer.max_amount} step="100" value={amount} onChange={(e) => setAmount(e.target.value)} placeholder="0.00" />
              <p className="zp-label mt-4">Repay within</p>
              <div className="grid grid-cols-3 gap-2" role="group" aria-label="Repayment period">
                {offer.tenors.map((t) => (
                  <button type="button" key={t.days} aria-pressed={days === t.days} onClick={() => setDays(t.days)}
                    className={`rounded-lg px-2 py-3 min-h-[56px] text-center border transition-colors ${days === t.days ? 'border-gold-500 bg-gold-500/10' : 'border-ink-600 hover:border-ink-500'}`}>
                    <span className={`block text-sm font-medium ${days === t.days ? 'text-gold-400' : 'text-slate-200'}`}>{t.days} days</span>
                    <span className="block text-xs text-slate-500">{t.interest_percent}% fee</span>
                  </button>
                ))}
              </div>
              {quoteErr && <p className="text-xs text-red-300 mt-3">{quoteErr}</p>}
              {quote && (
                <dl className="mt-4 rounded-lg border border-ink-600 bg-ink-900/60 p-4 text-sm space-y-1.5" aria-live="polite">
                  <div className="flex justify-between"><dt className="text-slate-400">You receive</dt><dd className="zp-amount text-slate-100">{formatNaira(quote.principal)}</dd></div>
                  <div className="flex justify-between"><dt className="text-slate-400">Interest (flat fee)</dt><dd className="zp-amount text-slate-100">{formatNaira(quote.interest)}</dd></div>
                  <div className="flex justify-between border-t border-ink-700 pt-1.5"><dt className="text-slate-200 font-medium">You repay</dt><dd className="zp-amount text-gold-400 font-semibold">{formatNaira(quote.total_due)}</dd></div>
                  <div className="flex justify-between"><dt className="text-slate-400">Due by</dt><dd className="text-slate-100">{formatDate(quote.due_at)}</dd></div>
                </dl>
              )}
              <label className="flex items-start gap-3 text-sm text-slate-300 cursor-pointer mt-4">
                <input type="checkbox" className="mt-1 w-5 h-5 accent-[#DDAA4E] shrink-0" checked={accept} onChange={(e) => setAccept(e.target.checked)} />
                <span>I understand I must repay the full amount shown by the due date, and that the interest is fixed once I accept.</span>
              </label>
              <button type="button" disabled={!quote || !accept} className="zp-btn-primary w-full min-h-[48px] mt-4" onClick={() => setPin({ open: true, mode: 'apply', loan: null, amount: 0, loading: false, error: '' })}>Accept and get the money</button>
            </>
          )}
        </section>
      )}

      {loans.length > 0 && (
        <section aria-label="Loan history">
          <h2 className="font-display text-lg text-white mb-3">History</h2>
          <div className="zp-card divide-y divide-ink-700/60">
            {loans.map((l) => (
              <div key={l.id} className="p-4 flex items-center justify-between gap-3">
                <div className="min-w-0">
                  <p className="text-sm text-slate-100">{formatNaira(l.principal)} · {l.tenor_days} days</p>
                  <p className="text-xs text-slate-500 font-mono break-all">{l.reference}</p>
                  <p className="text-xs text-slate-500">{formatDate(l.disbursed_at)}</p>
                </div>
                <span className={`zp-pill shrink-0 ${l.status === 'repaid' ? 'text-teal-300 border-teal-500/40 bg-teal-500/10' : l.is_overdue ? 'text-red-300 border-red-500/40 bg-red-500/10' : 'text-gold-400 border-gold-500/40 bg-gold-500/10'}`}>{l.status === 'repaid' ? 'Repaid' : l.is_overdue ? 'Overdue' : 'Active'}</span>
              </div>
            ))}
          </div>
        </section>
      )}

      <PinPrompt open={pin.open} onCancel={() => setPin({ open: false, mode: null, loan: null, amount: 0, loading: false, error: '' })} onConfirm={confirm} loading={pin.loading} error={pin.error} />
    </div>
  )
}
