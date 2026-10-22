import React, { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { walletApi } from '../services/endpoints'
import { apiErrorMessage } from '../services/api'
import { formatNaira, formatAccountNumber } from '../utils/format'
import { Alert } from '../components/UI.jsx'
import PinPrompt from '../components/PinPrompt.jsx'

export default function Transfer() {
  const navigate = useNavigate()
  const [recipient, setRecipient] = useState('')
  const [amount, setAmount] = useState('')
  const [narration, setNarration] = useState('')
  const [error, setError] = useState('')
  const [pinOpen, setPinOpen] = useState(false)
  const [pinError, setPinError] = useState('')
  const [loading, setLoading] = useState(false)
  const [success, setSuccess] = useState(null)
  const [lookup, setLookup] = useState({ state: 'idle' })   // idle | checking | found | notfound | error
  const seq = useRef(0)

  // name enquiry: show WHO will receive the money before the sender commits
  useEffect(() => {
    const q = recipient.trim()
    if (q.length < 3) { setLookup({ state: 'idle' }); return }
    setLookup({ state: 'checking' })
    const mine = ++seq.current
    const t = setTimeout(async () => {
      try {
        const { data } = await walletApi.resolveRecipient(q)
        if (mine !== seq.current) return
        setLookup(data.found ? { state: 'found', ...data } : { state: 'notfound', reason: data.reason })
      } catch (err) {
        if (mine === seq.current) setLookup({ state: 'error', reason: apiErrorMessage(err) })
      }
    }, 500)
    return () => clearTimeout(t)
  }, [recipient])

  const canReview = lookup.state === 'found' && !lookup.is_self && Number(amount) > 0

  const openConfirm = (e) => {
    e.preventDefault()
    setError('')
    if (!canReview) {
      setError(lookup.is_self ? "You can't send money to yourself." : 'Pick a valid recipient and enter an amount.')
      return
    }
    setPinOpen(true)
  }

  const confirmTransfer = async (pin) => {
    setLoading(true)
    setPinError('')
    try {
      const { data } = await walletApi.transfer({
        recipient_identifier: recipient.trim(), amount: Number(amount), pin, narration: narration || undefined,
      })
      setPinOpen(false)
      setSuccess({ ...data, to: lookup.name })
    } catch (err) {
      setPinError(apiErrorMessage(err))
    } finally {
      setLoading(false)
    }
  }

  if (success) {
    return (
      <div className="max-w-md mx-auto px-4 sm:px-6 py-12 text-center">
        <div className="w-14 h-14 rounded-full bg-teal-500/15 border border-teal-500/40 text-teal-300 flex items-center justify-center mx-auto mb-5 text-2xl">✓</div>
        <h1 className="font-display text-2xl text-white mb-2">Transfer complete</h1>
        <p className="text-slate-400 text-sm mb-1">{formatNaira(success.amount)} sent to {success.to}.</p>
        <p className="text-slate-500 text-xs font-mono mb-8 break-all">{success.reference}</p>
        <div className="grid grid-cols-2 gap-3">
          <button onClick={() => { setSuccess(null); setRecipient(''); setAmount(''); setNarration('') }} className="zp-btn-secondary min-h-[48px]">Send another</button>
          <button onClick={() => navigate('/dashboard')} className="zp-btn-primary min-h-[48px]">Dashboard</button>
        </div>
      </div>
    )
  }

  return (
    <div className="max-w-md mx-auto px-4 sm:px-6 py-8 sm:py-16">
      <h1 className="font-display text-3xl text-white mb-2">Send money</h1>
      <p className="text-slate-400 text-sm mb-6">Pay anyone on ZionhiltPay by account number, username, email or phone. A share of the fee comes back to you as cashback and device cover.</p>

      <Alert type="error">{error}</Alert>

      <form onSubmit={openConfirm} className="zp-card p-5 sm:p-6 space-y-4">
        <div>
          <label className="zp-label" htmlFor="recipient">Recipient</label>
          <input id="recipient" className="zp-input" required autoCapitalize="none" autoCorrect="off" spellCheck={false}
            value={recipient} onChange={(e) => setRecipient(e.target.value)} placeholder="Account number, @username, email or phone" />
          <div className="mt-2 min-h-[1.5rem]" aria-live="polite">
            {lookup.state === 'checking' && <p className="text-xs text-slate-500">Looking up recipient…</p>}
            {lookup.state === 'found' && !lookup.is_self && (
              <div className="rounded-lg border border-teal-500/40 bg-teal-500/10 px-3 py-2">
                <p className="text-sm text-teal-300 font-medium">✓ {lookup.name}</p>
                <p className="text-xs text-slate-400">{lookup.username ? `@${lookup.username} · ` : ''}{formatAccountNumber(lookup.account_number)}</p>
              </div>
            )}
            {lookup.state === 'found' && lookup.is_self && <p className="text-xs text-gold-400">That's your own account.</p>}
            {(lookup.state === 'notfound' || lookup.state === 'error') && <p className="text-xs text-red-300">{lookup.reason}</p>}
          </div>
        </div>
        <div>
          <label className="zp-label" htmlFor="amount">Amount (₦)</label>
          <input id="amount" className="zp-input zp-amount" required type="number" inputMode="decimal" min="1" step="0.01" value={amount} onChange={(e) => setAmount(e.target.value)} placeholder="0.00" />
        </div>
        <div>
          <label className="zp-label" htmlFor="narration">Note (optional)</label>
          <input id="narration" className="zp-input" value={narration} onChange={(e) => setNarration(e.target.value)} placeholder="What's this for?" />
        </div>
        <button type="submit" disabled={!canReview} className="zp-btn-primary w-full min-h-[48px]">Review transfer</button>
      </form>

      <PinPrompt open={pinOpen} onCancel={() => { setPinOpen(false); setPinError('') }} onConfirm={confirmTransfer} loading={loading} error={pinError} />
    </div>
  )
}
