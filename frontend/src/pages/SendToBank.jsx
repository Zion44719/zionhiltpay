import React, { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { bankApi } from '../services/endpoints'
import { apiErrorMessage } from '../services/api'
import { Alert, Loader } from '../components/UI.jsx'
import PinPrompt from '../components/PinPrompt.jsx'
import { formatNaira } from '../utils/format'

const newRef = () => (window.crypto?.randomUUID ? window.crypto.randomUUID() : `${Date.now().toString(16)}-${Math.random().toString(16).slice(2)}-${Math.random().toString(16).slice(2)}`)

export default function SendToBank() {
  const navigate = useNavigate()
  const [meta, setMeta] = useState(null)               // { mode, banks, demo_accounts }
  const [loadError, setLoadError] = useState('')
  const [acct, setAcct] = useState('')
  const [bank, setBank] = useState('')                 // chosen bank code
  const [suggest, setSuggest] = useState([])
  const [who, setWho] = useState({ state: 'idle' })    // idle | checking | found | error
  const [amount, setAmount] = useState('')
  const [narration, setNarration] = useState('')
  const [error, setError] = useState('')
  const [pinOpen, setPinOpen] = useState(false)
  const [pinError, setPinError] = useState('')
  const [busy, setBusy] = useState(false)
  const [done, setDone] = useState(null)
  const clientRef = useRef(newRef())                   // one id per form: a double-tap or retry can never pay twice
  const sSeq = useRef(0)
  const rSeq = useRef(0)

  useEffect(() => { bankApi.list().then(({ data }) => setMeta(data)).catch((e) => setLoadError(apiErrorMessage(e))) }, [])

  // 1. ten digits typed -> which banks could this be?
  useEffect(() => {
    setWho({ state: 'idle' })
    if (acct.length !== 10) { setSuggest([]); return undefined }
    const mine = ++sSeq.current
    bankApi.suggest(acct).then(({ data }) => {
      if (mine !== sSeq.current) return
      setSuggest(data.banks)
      if (data.banks.length === 1) setBank((b) => b || data.banks[0].code)   // only one possibility: pick it for them
    }).catch(() => mine === sSeq.current && setSuggest([]))
    return undefined
  }, [acct])

  // 2. number + bank known -> whose account is it?
  useEffect(() => {
    if (acct.length !== 10 || !bank) { setWho({ state: 'idle' }); return undefined }
    setWho({ state: 'checking' })
    const mine = ++rSeq.current
    const t = setTimeout(() => {
      bankApi.resolve(bank, acct)
        .then(({ data }) => mine === rSeq.current && setWho({ state: 'found', ...data }))
        .catch((e) => mine === rSeq.current && setWho({ state: 'error', reason: apiErrorMessage(e) }))
    }, 300)
    return () => clearTimeout(t)
  }, [acct, bank])

  const bankName = useMemo(() => meta?.banks.find((b) => b.code === bank)?.name, [meta, bank])
  const chosen = meta?.banks.find((b) => b.code === bank)
  const canReview = who.state === 'found' && Number(amount) > 0

  const review = (e) => {
    e.preventDefault(); setError('')
    if (!canReview) return setError('Enter a valid account and an amount.')
    setPinOpen(true)
  }

  const confirm = async (pin) => {
    setBusy(true); setPinError('')
    try {
      const { data } = await bankApi.transfer({
        bank_code: bank, account_number: acct, amount: Number(amount), pin,
        narration: narration || undefined, client_reference: clientRef.current,
      })
      setPinOpen(false); setDone(data)
      clientRef.current = newRef()
    } catch (err) { setPinError(apiErrorMessage(err)) } finally { setBusy(false) }
  }

  if (done) {
    return (
      <div className="max-w-md mx-auto px-4 sm:px-6 py-12 text-center">
        <div className="w-14 h-14 rounded-full bg-teal-500/15 border border-teal-500/40 text-teal-300 flex items-center justify-center mx-auto mb-5 text-2xl">✓</div>
        <h1 className="font-display text-2xl text-white mb-2">Transfer sent</h1>
        <p className="text-slate-300 text-sm">{formatNaira(done.amount)} to <strong>{done.beneficiary_name}</strong></p>
        <p className="text-slate-400 text-xs mb-1">{done.bank_name} · ••••{done.account_last4} · fee {formatNaira(done.fee_amount)}</p>
        <p className="text-slate-500 text-xs font-mono mb-8 break-all">{done.reference}</p>
        <div className="grid grid-cols-2 gap-3">
          <button className="zp-btn-secondary min-h-[48px]" onClick={() => { setDone(null); setAcct(''); setBank(''); setAmount(''); setNarration('') }}>Send another</button>
          <button className="zp-btn-primary min-h-[48px]" onClick={() => navigate('/dashboard')}>Dashboard</button>
        </div>
      </div>
    )
  }

  if (!meta && !loadError) return <Loader />

  return (
    <div className="max-w-md mx-auto px-4 sm:px-6 py-8 sm:py-14">
      <h1 className="font-display text-3xl text-white mb-2">Send to a bank account</h1>
      <p className="text-slate-400 text-sm mb-6">Type the account number. We'll work out the bank and show who owns the account before you pay.</p>
      <Alert type="error">{loadError || error}</Alert>

      {meta?.mode === 'mock' && (
        <div className="rounded-lg border border-gold-500/30 bg-gold-500/10 px-4 py-3 mb-5 text-xs text-gold-400">
          <p className="font-medium mb-1">Demo mode: the bank list and account names are simulated.</p>
          <p className="mb-2 text-gold-400/80">Tap a sample account to try it:</p>
          <div className="flex flex-wrap gap-2">
            {meta.demo_accounts?.map((d) => (
              <button type="button" key={d.account_number} onClick={() => { setAcct(d.account_number); setBank(d.code) }}
                className="rounded-md border border-gold-500/40 px-2.5 py-1.5 min-h-[36px] font-mono text-[11px] hover:bg-gold-500/10">{d.account_number} · {d.bank.split(' ')[0]}</button>
            ))}
          </div>
        </div>
      )}

      <form onSubmit={review} className="zp-card p-5 sm:p-6 space-y-4">
        <div>
          <label className="zp-label" htmlFor="acct">Account number</label>
          <input id="acct" className="zp-input zp-amount tracking-wider" inputMode="numeric" autoComplete="off" maxLength={10}
            value={acct} onChange={(e) => { setAcct(e.target.value.replace(/\D/g, '')); }} placeholder="10 digits" />
          {acct.length > 0 && acct.length < 10 && <p className="text-xs text-slate-500 mt-1.5">{10 - acct.length} more digit{10 - acct.length === 1 ? '' : 's'}</p>}
        </div>

        {suggest.length > 0 && (
          <div>
            <p className="zp-label">Looks like one of these banks</p>
            <div className="flex flex-wrap gap-2" role="group" aria-label="Suggested banks">
              {suggest.map((b) => (
                <button type="button" key={b.code} aria-pressed={bank === b.code} onClick={() => setBank(b.code)}
                  className={`rounded-full px-3.5 py-2 min-h-[40px] text-sm border transition-colors ${bank === b.code ? 'border-gold-500 bg-gold-500/10 text-gold-400' : 'border-ink-600 text-slate-300 hover:border-ink-500'}`}>{b.name}</button>
              ))}
            </div>
          </div>
        )}

        <div>
          <label className="zp-label" htmlFor="bank">Bank</label>
          <select id="bank" className="zp-input" value={bank} onChange={(e) => setBank(e.target.value)}>
            <option value="">{acct.length === 10 && suggest.length === 0 ? "Choose the bank (we couldn't narrow it down)" : 'Choose a bank'}</option>
            {meta?.banks.map((b) => <option key={b.code} value={b.code}>{b.name}</option>)}
          </select>
          {chosen && !chosen.checkable && <p className="text-xs text-slate-500 mt-1.5">We can't pre-check this bank's account numbers, so we'll confirm the name with the bank.</p>}
        </div>

        <div className="min-h-[3.25rem]" aria-live="polite">
          {who.state === 'checking' && <p className="text-xs text-slate-500">Looking up the account…</p>}
          {who.state === 'found' && (
            <div className="rounded-lg border border-teal-500/40 bg-teal-500/10 px-4 py-3">
              <p className="text-xs text-teal-300/80">Account name</p>
              <p className="text-teal-300 font-semibold tracking-wide break-words">{who.account_name}</p>
              <p className="text-xs text-slate-400">{who.bank_name} · {acct}</p>
            </div>
          )}
          {who.state === 'error' && <p className="text-xs text-red-300">{who.reason}</p>}
        </div>

        <div>
          <label className="zp-label" htmlFor="b-amount">Amount (₦)</label>
          <input id="b-amount" className="zp-input zp-amount" type="number" inputMode="decimal" min="1" step="0.01" value={amount} onChange={(e) => setAmount(e.target.value)} placeholder="0.00" />
        </div>
        <div>
          <label className="zp-label" htmlFor="b-note">Note (optional)</label>
          <input id="b-note" className="zp-input" maxLength={120} value={narration} onChange={(e) => setNarration(e.target.value)} placeholder="What's this for?" />
        </div>
        <button type="submit" disabled={!canReview} className="zp-btn-primary w-full min-h-[48px]">Review transfer</button>
        <p className="text-xs text-slate-500 text-center">A small flat fee applies. Limits depend on your <Link to="/settings/level" className="text-gold-400 hover:underline">account level</Link>.</p>
      </form>

      <PinPrompt open={pinOpen} onCancel={() => { setPinOpen(false); setPinError('') }} onConfirm={confirm} loading={busy} error={pinError} />
    </div>
  )
}
