import React, { useCallback, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { tierApi, profileApi } from '../services/endpoints'
import { apiErrorMessage } from '../services/api'
import { useAuth } from '../context/AuthContext.jsx'
import { Alert, Loader, KycBadge } from '../components/UI.jsx'
import { formatDate, formatNaira } from '../utils/format'

const MAX_DOC = 6_000_000
const ID_LABEL = { national_id: 'National ID (NIN)', drivers_license: "Driver's license" }
const ID_HINT = { national_id: '11 digits', drivers_license: '8-20 letters/digits' }

function DocThumb({ version }) {
  const [url, setUrl] = useState(null)
  useEffect(() => {
    let alive = true, obj = null
    tierApi.docFile().then(({ data }) => { if (alive) { obj = URL.createObjectURL(data); setUrl(obj) } }).catch(() => alive && setUrl(null))
    return () => { alive = false; if (obj) URL.revokeObjectURL(obj) }
  }, [version])
  return url ? <img src={url} alt="Your proof of address" className="mt-3 rounded-lg border border-ink-600 max-h-44 w-auto mx-auto" /> : null
}

/** One document: what it is, whether we have it, and an Edit button that opens its form in place. */
function Item({ done, title, value, badge, open, onToggle, editable = true, editLabel = 'Edit', children }) {
  return (
    <section className="zp-card p-4">
      <div className="flex items-start gap-3">
        <span className={`mt-0.5 w-6 h-6 rounded-full flex items-center justify-center text-sm shrink-0 ${done ? 'bg-teal-500/15 text-teal-300 border border-teal-500/40' : 'border border-ink-500 text-slate-500'}`} aria-hidden="true">{done ? '✓' : ''}</span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2"><h3 className="text-slate-100 font-medium">{title}</h3>{badge}</div>
          <p className={`text-sm mt-0.5 break-words ${done ? 'text-slate-300' : 'text-slate-500'}`}>{value}</p>
        </div>
        {editable && <button type="button" onClick={onToggle} aria-expanded={open} className="zp-btn-secondary !px-4 !py-2 text-sm min-h-[44px] shrink-0">{open ? 'Close' : editLabel}</button>}
      </div>
      {open && <div className="mt-4 pt-4 border-t border-ink-700">{children}</div>}
    </section>
  )
}

export default function Documents() {
  const { refreshProfile } = useAuth()
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [ok, setOk] = useState('')
  const [busy, setBusy] = useState(false)
  const [target, setTarget] = useState(null)
  const [open, setOpen] = useState(null)          // which row is being edited
  const [version, setVersion] = useState(0)
  const [idForm, setIdForm] = useState({ id_type: 'national_id', id_number: '', consent: false })
  const [bvn, setBvn] = useState('')
  const [address, setAddress] = useState('')
  const [confirmWithdraw, setConfirmWithdraw] = useState(false)
  const fileRef = useRef(null)

  const load = useCallback(async () => {
    try {
      const { data: d } = await tierApi.overview()
      setData(d)
      setTarget((t) => t ?? d.request?.target_tier ?? (d.targets.includes(3) ? 3 : d.targets[0] ?? null))
    } catch (e) { setError(apiErrorMessage(e)) } finally { setLoading(false) }
  }, [])
  useEffect(() => { load() }, [load])

  if (loading) return <Loader />
  if (!data) return <div className="max-w-lg mx-auto px-4 py-10"><Alert type="error">{error || 'Could not load your documents.'}</Alert></div>

  const { request: req, identity, has_photo: hasPhoto, last_rejection: rej, current_tier: cur } = data
  if (!data.targets.length) {
    return (
      <div className="max-w-lg mx-auto px-4 py-10 text-center">
        <p className="text-teal-300 mb-2">You're on the highest level (Tier {cur}).</p>
        <Link to="/settings/level" className="text-gold-400 hover:underline">See your limits</Link>
      </div>
    )
  }

  const effTarget = req?.target_tier ?? target
  const pending = req?.status === 'pending'
  const have = {
    identity: ['submitted', 'verified'].includes(identity.kyc_status), photo: hasPhoto,
    bvn: !!req?.bvn_last4, address: !!req?.address, document: !!req?.has_document,
  }
  const required = effTarget === 3 ? ['identity', 'photo', 'bvn', 'address', 'document'] : ['identity', 'photo', 'bvn']
  const lacking = required.filter((k) => !have[k])
  const names = { identity: 'your ID number', photo: 'a profile photo', bvn: 'your BVN', address: 'your address', document: 'proof of address' }
  const tierInfo = (t) => data.tiers.find((x) => x.tier === t)
  const toggle = (k) => { setOpen((o) => (o === k ? null : k)); setError(''); setOk('') }

  const run = async (fn, message) => {
    setBusy(true); setError(''); setOk('')
    try { await fn(); setOk(message); setOpen(null); await load(); await refreshProfile(); setVersion((v) => v + 1) }
    catch (e) { setError(apiErrorMessage(e)) } finally { setBusy(false) }
  }
  const form = (fields) => { const f = new FormData(); f.append('target_tier', String(effTarget)); Object.entries(fields).forEach(([k, v]) => f.append(k, v)); return f }

  const chooseTarget = (t) => {
    setTarget(t)
    if (req) run(() => tierApi.saveDocs(form({ target_tier: t })), `Now aiming for Tier ${t}.`)
  }
  const saveId = (e) => {
    e.preventDefault()
    if (!idForm.consent) return setError('Please tick the box to consent to identity verification.')
    run(() => profileApi.updateIdentity({ id_type: idForm.id_type, id_number: idForm.id_number, consent_id_processing: true }), 'ID number saved. It goes back to our team for review.')
  }
  const saveBvn = (e) => { e.preventDefault(); if (!/^\d{11}$/.test(bvn)) return setError('Your BVN is exactly 11 digits.'); run(() => tierApi.saveDocs(form({ bvn })), 'BVN saved.'); setBvn('') }
  const saveAddress = (e) => { e.preventDefault(); if (address.trim().length < 15) return setError('Enter your full residential address (street, area, city and state).'); run(() => tierApi.saveDocs(form({ address: address.trim() })), 'Address saved.') }
  const pickFile = (e) => {
    const f = e.target.files?.[0]; e.target.value = ''
    setError('')
    if (!f) return
    if (!f.type.startsWith('image/')) return setError('Please attach a photo of the document (JPEG, PNG or WebP). PDFs are not accepted.')
    if (f.size > MAX_DOC) return setError('That photo is too large. Please choose one under 6 MB.')
    run(() => tierApi.saveDocs(form({ document: f })), 'Photo saved.')
  }
  const submit = () => run(() => tierApi.submit(), 'Submitted! We will review your documents and update your account level.')
  const withdraw = () => run(async () => { await tierApi.withdraw(); setConfirmWithdraw(false) }, pending ? 'Your request was withdrawn.' : 'Draft discarded.')

  return (
    <div className="max-w-xl mx-auto px-4 sm:px-6 py-6 sm:py-10">
      <Link to="/settings" className="text-sm text-slate-400 hover:text-white">← Settings</Link>
      <h1 className="font-display text-2xl sm:text-3xl text-white mt-2 mb-1">Verification documents</h1>
      <p className="text-slate-400 text-sm mb-5">Submit these to raise your limits. Each item can be edited at any time, even after you submit.</p>
      <Alert type="error">{error}</Alert>
      <Alert type="success">{ok}</Alert>

      {rej && !req && <Alert type="error">Your last request was not approved{rej.review_note ? `: ${rej.review_note}` : '.'} Fix the items below and submit again.</Alert>}

      {data.targets.length > 1 && (
        <div className="mb-5">
          <p className="zp-label">I want to reach</p>
          <div className="grid grid-cols-2 gap-3" role="group" aria-label="Account level to reach">
            {data.targets.map((t) => (
              <button type="button" key={t} aria-pressed={effTarget === t} disabled={busy} onClick={() => chooseTarget(t)}
                className={`rounded-lg px-3 py-3 min-h-[64px] text-left border transition-colors ${effTarget === t ? 'border-gold-500 bg-gold-500/10' : 'border-ink-600 hover:border-ink-500'}`}>
                <span className={`block text-sm font-medium ${effTarget === t ? 'text-gold-400' : 'text-slate-200'}`}>Tier {t}{t === 3 && cur === 1 ? ' (straight from Tier 1)' : ''}</span>
                <span className="block text-xs text-slate-500 mt-0.5">Send {formatNaira(tierInfo(t).daily_limit)} a day</span>
              </button>
            ))}
          </div>
        </div>
      )}

      <div className={`rounded-lg border px-4 py-3 mb-5 text-sm ${pending ? 'border-gold-500/40 bg-gold-500/10 text-gold-400' : 'border-ink-600 bg-ink-800/60 text-slate-300'}`} role="status">
        {pending
          ? <>Under review since {formatDate(req.submitted_at)}. You can still change anything below{req.edit_count > 0 ? ` (edited ${req.edit_count} time${req.edit_count === 1 ? '' : 's'} since)` : ''}; we tell the reviewer when you do.</>
          : req
            ? <>Draft saved {formatDate(req.updated_at)}. Finish the items below, then submit.</>
            : <>Nothing saved yet. As soon as you add one item we keep it as a draft, so you can finish later.</>}
      </div>

      <div className="space-y-3 mb-6">
        <Item done={have.identity} title="ID number" open={open === 'identity'} onToggle={() => toggle('identity')}
          editable={identity.kyc_status !== 'verified'} badge={identity.kyc_status !== 'not_submitted' ? <KycBadge status={identity.kyc_status} /> : null}
          value={identity.id_type ? `${ID_LABEL[identity.id_type]} ending ${identity.id_number_last4}${identity.kyc_status === 'verified' ? ' (verified, contact support to change)' : ''}` : 'Not provided'}>
          <form onSubmit={saveId} className="space-y-3">
            <div className="grid grid-cols-2 gap-2">
              {Object.keys(ID_LABEL).map((t) => (
                <button type="button" key={t} aria-pressed={idForm.id_type === t} onClick={() => setIdForm({ ...idForm, id_type: t, id_number: '' })}
                  className={`rounded-lg px-3 py-3 min-h-[56px] text-left border ${idForm.id_type === t ? 'border-gold-500 bg-gold-500/10' : 'border-ink-600'}`}>
                  <span className={`block text-sm ${idForm.id_type === t ? 'text-gold-400' : 'text-slate-200'}`}>{ID_LABEL[t]}</span><span className="block text-xs text-slate-500">{ID_HINT[t]}</span>
                </button>
              ))}
            </div>
            <div><label className="zp-label" htmlFor="d-id">ID number</label>
              <input id="d-id" className="zp-input font-mono tracking-wider" autoComplete="off" spellCheck={false} maxLength={idForm.id_type === 'national_id' ? 11 : 24}
                inputMode={idForm.id_type === 'national_id' ? 'numeric' : 'text'} value={idForm.id_number}
                onChange={(e) => setIdForm({ ...idForm, id_number: idForm.id_type === 'national_id' ? e.target.value.replace(/\D/g, '') : e.target.value.toUpperCase() })} /></div>
            <label className="flex items-start gap-3 text-sm text-slate-300 cursor-pointer"><input type="checkbox" className="mt-1 w-5 h-5 accent-[#DDAA4E] shrink-0" checked={idForm.consent} onChange={(e) => setIdForm({ ...idForm, consent: e.target.checked })} /><span>I consent to ZionhiltPay processing my ID number to verify my identity.</span></label>
            <button type="submit" disabled={busy} className="zp-btn-primary w-full min-h-[48px]">{busy ? 'Saving…' : 'Save ID number'}</button>
          </form>
        </Item>

        <Item done={have.photo} title="Profile photo" value={hasPhoto ? 'Added' : 'Not added'} editLabel={hasPhoto ? 'Change' : 'Add'} editable={false}
          badge={<Link to="/profile" className="text-xs text-gold-400 hover:underline">{hasPhoto ? 'Change photo' : 'Add photo'}</Link>} />

        <Item done={have.bvn} title="BVN" open={open === 'bvn'} onToggle={() => toggle('bvn')} editLabel={have.bvn ? 'Edit' : 'Add'}
          value={have.bvn ? `•••••••${req.bvn_last4}` : 'Not provided'}>
          <form onSubmit={saveBvn} className="space-y-3">
            <div><label className="zp-label" htmlFor="d-bvn">Bank Verification Number</label>
              <input id="d-bvn" className="zp-input font-mono tracking-wider" inputMode="numeric" autoComplete="off" maxLength={11} value={bvn} onChange={(e) => setBvn(e.target.value.replace(/\D/g, ''))} placeholder="11 digits" />
              <p className="text-xs text-slate-500 mt-1.5">Dial *565*0# on the phone number linked to your bank to see yours. We store it encrypted.</p></div>
            <button type="submit" disabled={busy} className="zp-btn-primary w-full min-h-[48px]">{busy ? 'Saving…' : 'Save BVN'}</button>
          </form>
        </Item>

        {effTarget === 3 && (
          <>
            <Item done={have.address} title="Residential address" open={open === 'address'} onToggle={() => { setAddress(req?.address || ''); toggle('address') }} editLabel={have.address ? 'Edit' : 'Add'}
              value={have.address ? req.address : 'Not provided'}>
              <form onSubmit={saveAddress} className="space-y-3">
                <div><label className="zp-label" htmlFor="d-addr">Address</label>
                  <textarea id="d-addr" className="zp-input" rows={3} maxLength={300} value={address} onChange={(e) => setAddress(e.target.value)} placeholder="House number, street, area, city, state" /></div>
                <button type="submit" disabled={busy} className="zp-btn-primary w-full min-h-[48px]">{busy ? 'Saving…' : 'Save address'}</button>
              </form>
            </Item>

            <Item done={have.document} title="Proof of address (photo)" open={open === 'document'} onToggle={() => toggle('document')} editLabel={have.document ? 'Replace' : 'Add'}
              value={have.document ? 'Photo uploaded' : 'Not uploaded'}>
              <input ref={fileRef} type="file" accept="image/jpeg,image/png,image/webp" className="sr-only" onChange={pickFile} aria-label="Choose a proof of address photo" />
              <button type="button" disabled={busy} onClick={() => fileRef.current?.click()} className="zp-btn-secondary w-full min-h-[48px]">{busy ? 'Uploading…' : have.document ? 'Choose a different photo' : 'Take or choose a photo'}</button>
              <p className="text-xs text-slate-500 mt-1.5">A utility bill or similar, dated within 3 months. The name and address must be readable. Photos only, no PDFs.</p>
              {have.document && <DocThumb version={`${version}-${req?.updated_at}`} />}
            </Item>
          </>
        )}
      </div>

      {!pending && (
        <div className="space-y-3">
          {lacking.length > 0 && <p className="text-xs text-slate-400" role="status">Still needed: {lacking.map((k) => names[k]).join(', ')}.</p>}
          <button type="button" disabled={busy || !req || lacking.length > 0} onClick={submit} className="zp-btn-primary w-full min-h-[48px]">{busy ? 'Working…' : `Submit for Tier ${effTarget} review`}</button>
        </div>
      )}
      {req && (
        confirmWithdraw ? (
          <div className="zp-card p-4 mt-4">
            <p className="text-sm text-slate-300 mb-3">{pending ? 'Withdraw this request? Your uploaded document is deleted.' : 'Discard this draft? Your uploaded document is deleted.'}</p>
            <div className="grid grid-cols-2 gap-3"><button className="zp-btn-secondary min-h-[44px]" onClick={() => setConfirmWithdraw(false)}>Keep it</button><button className="zp-btn-primary min-h-[44px]" disabled={busy} onClick={withdraw}>{pending ? 'Withdraw' : 'Discard'}</button></div>
          </div>
        ) : (
          <button type="button" onClick={() => setConfirmWithdraw(true)} className="w-full text-sm text-slate-400 hover:text-red-300 min-h-[44px] mt-3">{pending ? 'Withdraw this request' : 'Discard this draft'}</button>
        )
      )}
    </div>
  )
}
