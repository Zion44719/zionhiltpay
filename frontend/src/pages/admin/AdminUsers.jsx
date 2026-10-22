import React, { useCallback, useEffect, useState } from 'react'
import { adminApi } from '../../services/endpoints'
import { apiErrorMessage } from '../../services/api'
import { formatDate, formatAccountNumber } from '../../utils/format'
import { Loader, Alert, KycBadge, CopyButton } from '../../components/UI.jsx'
import { useAuth } from '../../context/AuthContext.jsx'

const PAGE = 20
const FILTERS = [
  ['', 'All'], ['submitted', 'KYC pending'], ['verified', 'Verified'], ['rejected', 'Rejected'],
]
const ID_LABEL = { national_id: 'National ID', drivers_license: "Driver's license" }

function Modal({ title, children, onClose }) {
  return (
    <div className="fixed inset-0 bg-black/70 backdrop-blur-sm z-50 flex items-end sm:items-center justify-center sm:px-4" onClick={onClose}>
      <div className="zp-card w-full sm:max-w-sm p-5 sm:p-6 rounded-b-none sm:rounded-b-2xl max-h-[90vh] overflow-y-auto" role="dialog" aria-modal="true" aria-label={title} onClick={(e) => e.stopPropagation()}>
        <h3 className="font-display text-lg text-white mb-3">{title}</h3>
        {children}
      </div>
    </div>
  )
}

export default function AdminUsers() {
  const { profile } = useAuth()
  const isSuper = profile?.role === 'super_admin'
  const [users, setUsers] = useState([])
  const [q, setQ] = useState('')
  const [query, setQuery] = useState('')
  const [kyc, setKyc] = useState('')
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [dialog, setDialog] = useState(null)   // {type:'freeze'|'kyc'|'reveal', user, decision?}
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [revealed, setRevealed] = useState(null)

  const load = useCallback(async () => {
    setLoading(true); setError('')
    try {
      const { data } = await adminApi.users({ q: query || undefined, kyc_status: kyc || undefined, page, page_size: PAGE })
      setUsers(data)
    } catch (err) { setError(apiErrorMessage(err)) } finally { setLoading(false) }
  }, [query, kyc, page])
  useEffect(() => { load() }, [load])

  // an ID shown on screen disappears after 20 seconds
  useEffect(() => {
    if (!revealed) return
    const t = setTimeout(() => setRevealed(null), 20000)
    return () => clearTimeout(t)
  }, [revealed])

  const close = () => { setDialog(null); setText(''); setRevealed(null) }
  const run = async (fn, okMsg) => {
    setBusy(true); setError('')
    try { await fn(); setSuccess(okMsg); close(); load() } catch (err) { setError(apiErrorMessage(err)); close() } finally { setBusy(false) }
  }

  const reveal = async () => {
    setBusy(true)
    try { const { data } = await adminApi.revealId(dialog.user.id); setRevealed(data) } catch (err) { setError(apiErrorMessage(err)); close() } finally { setBusy(false) }
  }

  return (
    <div>
      <Alert type="error">{error}</Alert>
      <Alert type="success">{success}</Alert>

      <form onSubmit={(e) => { e.preventDefault(); setPage(1); setQuery(q.trim()) }} className="flex flex-col sm:flex-row gap-2 mb-3">
        <input className="zp-input" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search name, username, account number, email or phone" aria-label="Search users" />
        <button className="zp-btn-secondary min-h-[48px] sm:shrink-0">Search</button>
      </form>
      <div className="flex gap-2 overflow-x-auto pb-2 mb-3" role="group" aria-label="Filter by KYC status">
        {FILTERS.map(([val, label]) => (
          <button key={val} onClick={() => { setKyc(val); setPage(1) }} aria-pressed={kyc === val}
            className={`zp-pill whitespace-nowrap min-h-[36px] px-4 ${kyc === val ? 'text-gold-400 border-gold-500/40 bg-gold-500/10' : 'text-slate-400 border-ink-600'}`}>{label}</button>
        ))}
      </div>

      {loading ? <Loader /> : (
        <div className="space-y-3">
          {users.length === 0 && <p className="text-sm text-slate-500 zp-card p-8 text-center">No users match.</p>}
          {users.map((u) => (
            <article key={u.id} className="zp-card p-4">
              <div className="flex flex-wrap items-center gap-2 mb-2">
                <h3 className="text-slate-100 font-medium break-words">{u.full_name}</h3>
                <span className="zp-pill text-slate-400 border-ink-600 whitespace-nowrap">{u.role}</span>
                <KycBadge status={u.kyc_status} />
                {u.is_frozen && <span className="zp-pill text-red-300 border-red-500/40 bg-red-500/10">Frozen</span>}
              </div>
              <dl className="grid gap-x-6 gap-y-1 text-xs text-slate-400 sm:grid-cols-2">
                <div className="flex gap-2"><dt className="text-slate-500 w-20 shrink-0">Username</dt><dd className="break-all">{u.username ? `@${u.username}` : '—'}</dd></div>
                <div className="flex gap-2"><dt className="text-slate-500 w-20 shrink-0">Account no.</dt><dd className="font-mono">{formatAccountNumber(u.account_number)}</dd></div>
                <div className="flex gap-2"><dt className="text-slate-500 w-20 shrink-0">Email</dt><dd className="break-all">{u.email}</dd></div>
                <div className="flex gap-2"><dt className="text-slate-500 w-20 shrink-0">Phone</dt><dd>{u.phone_number}</dd></div>
                <div className="flex gap-2"><dt className="text-slate-500 w-20 shrink-0">ID</dt>
                  <dd>{u.id_type ? `${ID_LABEL[u.id_type]} ••••${u.id_number_last4}` : 'None on file'}</dd></div>
                <div className="flex gap-2"><dt className="text-slate-500 w-20 shrink-0">Joined</dt><dd>{formatDate(u.created_at)}</dd></div>
              </dl>
              <div className="flex flex-wrap gap-2 mt-3">
                {u.id_type && u.kyc_status !== 'verified' && (
                  <button onClick={() => setDialog({ type: 'kyc', user: u, decision: 'verify' })} className="zp-btn-primary !px-3 !py-2 text-xs min-h-[40px]">Verify ID</button>
                )}
                {u.id_type && u.kyc_status !== 'rejected' && (
                  <button onClick={() => setDialog({ type: 'kyc', user: u, decision: 'reject' })} className="zp-btn-secondary !px-3 !py-2 text-xs min-h-[40px]">Reject ID</button>
                )}
                {isSuper && u.id_type && (
                  <button onClick={() => setDialog({ type: 'reveal', user: u })} className="zp-btn-secondary !px-3 !py-2 text-xs min-h-[40px]">View full ID</button>
                )}
                {u.is_frozen
                  ? <button onClick={() => run(() => adminApi.unfreeze(u.id), 'Account unfrozen.')} className="zp-btn-secondary !px-3 !py-2 text-xs min-h-[40px]">Unfreeze</button>
                  : <button onClick={() => setDialog({ type: 'freeze', user: u })} className="zp-btn-secondary !px-3 !py-2 text-xs min-h-[40px]">Freeze</button>}
                {u.account_number && <CopyButton text={u.account_number} label="Copy acct no." className="!px-3 !py-2 text-xs min-h-[40px]" />}
              </div>
            </article>
          ))}
          <div className="flex items-center justify-between pt-2">
            <button disabled={page <= 1} onClick={() => setPage((p) => p - 1)} className="zp-btn-ghost text-sm disabled:opacity-30">← Previous</button>
            <span className="text-xs text-slate-500">Page {page}</span>
            <button disabled={users.length < PAGE} onClick={() => setPage((p) => p + 1)} className="zp-btn-ghost text-sm disabled:opacity-30">Next →</button>
          </div>
        </div>
      )}

      {dialog?.type === 'freeze' && (
        <Modal title={`Freeze ${dialog.user.full_name}?`} onClose={close}>
          <input className="zp-input mb-4" value={text} onChange={(e) => setText(e.target.value)} placeholder="Reason for freezing" />
          <div className="flex gap-3">
            <button onClick={close} className="zp-btn-secondary flex-1 min-h-[44px]">Cancel</button>
            <button disabled={busy} onClick={() => run(() => adminApi.freeze(dialog.user.id, text || 'No reason provided'), 'Account frozen.')} className="zp-btn-primary flex-1 min-h-[44px]">Freeze</button>
          </div>
        </Modal>
      )}
      {dialog?.type === 'kyc' && (
        <Modal title={`${dialog.decision === 'verify' ? 'Verify' : 'Reject'} ID for ${dialog.user.full_name}?`} onClose={close}>
          <p className="text-xs text-slate-400 mb-3">{ID_LABEL[dialog.user.id_type]} ending {dialog.user.id_number_last4}. {dialog.decision === 'verify' ? 'Only verify after checking the number with the issuing authority.' : 'The user will be told their ID could not be verified.'}</p>
          <input className="zp-input mb-4" value={text} onChange={(e) => setText(e.target.value)} placeholder="Note (optional)" />
          <div className="flex gap-3">
            <button onClick={close} className="zp-btn-secondary flex-1 min-h-[44px]">Cancel</button>
            <button disabled={busy} onClick={() => run(() => adminApi.reviewKyc(dialog.user.id, dialog.decision, text || undefined), `ID ${dialog.decision === 'verify' ? 'verified' : 'rejected'}.`)} className="zp-btn-primary flex-1 min-h-[44px]">Confirm</button>
          </div>
        </Modal>
      )}
      {dialog?.type === 'reveal' && (
        <Modal title="View full ID number" onClose={close}>
          {!revealed ? (
            <>
              <p className="text-sm text-slate-300 mb-1">{dialog.user.full_name} · {ID_LABEL[dialog.user.id_type]}</p>
              <p className="text-xs text-gold-400 mb-4">This access is recorded in the audit log with your name. Only continue if you need it to verify this customer.</p>
              <div className="flex gap-3">
                <button onClick={close} className="zp-btn-secondary flex-1 min-h-[44px]">Cancel</button>
                <button disabled={busy} onClick={reveal} className="zp-btn-primary flex-1 min-h-[44px]">{busy ? 'Decrypting…' : 'Show ID'}</button>
              </div>
            </>
          ) : (
            <>
              <p className="text-xs text-slate-400 mb-1">{ID_LABEL[revealed.id_type]}</p>
              <p className="zp-amount text-2xl text-white tracking-widest break-all mb-2">{revealed.id_number}</p>
              <p className="text-xs text-slate-500 mb-4">Hides automatically in 20 seconds.</p>
              <button onClick={close} className="zp-btn-secondary w-full min-h-[44px]">Close</button>
            </>
          )}
        </Modal>
      )}
    </div>
  )
}
