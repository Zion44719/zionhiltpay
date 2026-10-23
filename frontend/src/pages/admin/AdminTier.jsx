import React, { useCallback, useEffect, useState } from 'react'
import { adminApi } from '../../services/endpoints'
import { apiErrorMessage } from '../../services/api'
import { formatDate, formatAccountNumber } from '../../utils/format'
import { Loader, Alert, Avatar, KycBadge } from '../../components/UI.jsx'
import { useAuth } from '../../context/AuthContext.jsx'

const FILTERS = [['pending', 'Pending'], ['approved', 'Approved'], ['rejected', 'Rejected']]

function Modal({ title, children, onClose }) {
  return (
    <div className="fixed inset-0 bg-black/70 backdrop-blur-sm z-50 flex items-end sm:items-center justify-center sm:px-4" onClick={onClose}>
      <div className="zp-card w-full sm:max-w-md p-5 sm:p-6 rounded-b-none sm:rounded-b-2xl max-h-[90vh] overflow-y-auto" role="dialog" aria-modal="true" aria-label={title} onClick={(e) => e.stopPropagation()}>
        <h3 className="font-display text-lg text-white mb-3">{title}</h3>{children}
      </div>
    </div>
  )
}

export default function AdminTier() {
  const { profile } = useAuth()
  const isSuper = profile?.role === 'super_admin'
  const [status, setStatus] = useState('pending')
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [ok, setOk] = useState('')
  const [dialog, setDialog] = useState(null)   // {type:'decide'|'doc'|'bvn', row, decision?}
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [docUrl, setDocUrl] = useState(null)
  const [bvn, setBvn] = useState(null)

  const load = useCallback(async () => {
    setLoading(true); setError('')
    try { const { data } = await adminApi.tierRequests(status); setRows(data) } catch (e) { setError(apiErrorMessage(e)) } finally { setLoading(false) }
  }, [status])
  useEffect(() => { load() }, [load])
  useEffect(() => () => { if (docUrl) URL.revokeObjectURL(docUrl) }, [docUrl])
  useEffect(() => { if (!bvn) return undefined; const t = setTimeout(() => setBvn(null), 20000); return () => clearTimeout(t) }, [bvn])

  const close = () => { setDialog(null); setNote(''); setDocUrl(null); setBvn(null) }

  const decide = async () => {
    setBusy(true)
    try { await adminApi.decideTier(dialog.row.id, dialog.decision, note || undefined); setOk(`Request ${dialog.decision === 'approve' ? 'approved' : 'rejected'}.`); close(); load() }
    catch (e) { setError(apiErrorMessage(e)); close() } finally { setBusy(false) }
  }
  const openDoc = async (row) => {
    setDialog({ type: 'doc', row }); setBusy(true)
    try { const { data } = await adminApi.tierDocument(row.id); setDocUrl(URL.createObjectURL(data)) } catch (e) { setError(apiErrorMessage(e)); close() } finally { setBusy(false) }
  }
  const reveal = async () => {
    setBusy(true)
    try { const { data } = await adminApi.revealBvn(dialog.row.id); setBvn(data.bvn) } catch (e) { setError(apiErrorMessage(e)); close() } finally { setBusy(false) }
  }

  return (
    <div>
      <Alert type="error">{error}</Alert>
      <Alert type="success">{ok}</Alert>
      <div className="flex gap-2 mb-4 overflow-x-auto pb-1" role="group" aria-label="Filter requests">
        {FILTERS.map(([v, label]) => (
          <button key={v} onClick={() => setStatus(v)} aria-pressed={status === v}
            className={`zp-pill whitespace-nowrap min-h-[36px] px-4 ${status === v ? 'text-gold-400 border-gold-500/40 bg-gold-500/10' : 'text-slate-400 border-ink-600'}`}>{label}</button>
        ))}
      </div>

      {loading ? <Loader /> : (
        <div className="space-y-3">
          {rows.length === 0 && <p className="text-sm text-slate-500 zp-card p-8 text-center">No {status} requests.</p>}
          {rows.map((r) => (
            <article key={r.id} className="zp-card p-4">
              <div className="flex items-start gap-3">
                <Avatar name={r.user.full_name} has={r.user.has_photo} userId={r.user.id} size={48} />
                <div className="min-w-0 flex-1">
                  <h3 className="text-slate-100 font-medium break-words">{r.user.full_name}</h3>
                  <p className="text-xs text-slate-400 break-all">{r.user.username ? `@${r.user.username} · ` : ''}{formatAccountNumber(r.user.account_number)}</p>
                  <div className="flex flex-wrap items-center gap-2 mt-2">
                    <span className="zp-pill text-gold-400 border-gold-500/40 bg-gold-500/10 whitespace-nowrap">Tier {r.user.current_tier} → {r.target_tier}</span>
                    <KycBadge status={r.user.kyc_status} />
                    {r.edited_after_submit && <span className="zp-pill text-gold-400 border-gold-500/40 bg-gold-500/10 whitespace-nowrap">Edited after submission</span>}
                    {r.target_tier - r.user.current_tier > 1 && <span className="zp-pill text-teal-300 border-teal-500/40 bg-teal-500/10 whitespace-nowrap">Direct jump</span>}
                  </div>
                </div>
              </div>
              <dl className="mt-3 text-xs text-slate-400 space-y-1">
                <div className="flex gap-2"><dt className="text-slate-500 w-20 shrink-0">Submitted</dt><dd>{formatDate(r.submitted_at || r.created_at)}</dd></div>
                {r.edited_after_submit && <div className="flex gap-2"><dt className="text-slate-500 w-20 shrink-0">Last edited</dt><dd>{formatDate(r.updated_at)} ({r.edit_count} edit{r.edit_count === 1 ? '' : 's'})</dd></div>}
                {r.bvn_last4 && <div className="flex gap-2"><dt className="text-slate-500 w-20 shrink-0">BVN</dt><dd>•••••••{r.bvn_last4}</dd></div>}
                {r.address && <div className="flex gap-2"><dt className="text-slate-500 w-20 shrink-0">Address</dt><dd className="break-words">{r.address}</dd></div>}
                {r.review_note && <div className="flex gap-2"><dt className="text-slate-500 w-20 shrink-0">Note</dt><dd className="break-words">{r.review_note}</dd></div>}
              </dl>
              <div className="flex flex-wrap gap-2 mt-3">
                {r.has_document && <button onClick={() => openDoc(r)} className="zp-btn-secondary !px-3 !py-2 text-xs min-h-[40px]">View document</button>}
                {isSuper && r.bvn_last4 && <button onClick={() => setDialog({ type: 'bvn', row: r })} className="zp-btn-secondary !px-3 !py-2 text-xs min-h-[40px]">View full BVN</button>}
                {r.status === 'pending' && (
                  <>
                    <button onClick={() => setDialog({ type: 'decide', row: r, decision: 'approve' })} className="zp-btn-primary !px-3 !py-2 text-xs min-h-[40px]">Approve</button>
                    <button onClick={() => setDialog({ type: 'decide', row: r, decision: 'reject' })} className="zp-btn-secondary !px-3 !py-2 text-xs min-h-[40px]">Reject</button>
                  </>
                )}
              </div>
            </article>
          ))}
        </div>
      )}

      {dialog?.type === 'decide' && (
        <Modal title={`${dialog.decision === 'approve' ? 'Approve' : 'Reject'} Tier ${dialog.row.target_tier} for ${dialog.row.user.full_name}?`} onClose={close}>
          {dialog.decision === 'approve' && <p className="text-xs text-slate-400 mb-3">The customer's ID must already be verified (Users &amp; KYC). Check the BVN against their records first.</p>}
          {dialog.decision === 'approve' && dialog.row.target_tier === 3 && <p className="text-xs text-slate-400 mb-3">Open the document and confirm the name and address match, and that it is recent.{dialog.row.user.current_tier === 1 ? ' This takes the customer straight from Tier 1 to Tier 3.' : ''}</p>}
          <input className="zp-input mb-4" value={note} onChange={(e) => setNote(e.target.value)} placeholder={dialog.decision === 'reject' ? 'Reason (shown to the customer)' : 'Note (optional)'} />
          <div className="flex gap-3">
            <button onClick={close} className="zp-btn-secondary flex-1 min-h-[44px]">Cancel</button>
            <button disabled={busy} onClick={decide} className="zp-btn-primary flex-1 min-h-[44px]">Confirm</button>
          </div>
        </Modal>
      )}
      {dialog?.type === 'doc' && (
        <Modal title="Proof of address" onClose={close}>
          {docUrl ? <img src={docUrl} alt="Proof of address document" className="rounded-lg border border-ink-600 w-full" /> : <Loader />}
          <p className="text-xs text-slate-500 mt-2">Viewing is recorded in the audit log.</p>
          <button onClick={close} className="zp-btn-secondary w-full min-h-[44px] mt-3">Close</button>
        </Modal>
      )}
      {dialog?.type === 'bvn' && (
        <Modal title="View full BVN" onClose={close}>
          {!bvn ? (
            <>
              <p className="text-xs text-gold-400 mb-4">This access is recorded in the audit log with your name. Only continue if you need it to verify this customer.</p>
              <div className="flex gap-3"><button onClick={close} className="zp-btn-secondary flex-1 min-h-[44px]">Cancel</button><button disabled={busy} onClick={reveal} className="zp-btn-primary flex-1 min-h-[44px]">{busy ? 'Decrypting…' : 'Show BVN'}</button></div>
            </>
          ) : (
            <>
              <p className="zp-amount text-2xl text-white tracking-widest break-all mb-2">{bvn}</p>
              <p className="text-xs text-slate-500 mb-4">Hides automatically in 20 seconds.</p>
              <button onClick={close} className="zp-btn-secondary w-full min-h-[44px]">Close</button>
            </>
          )}
        </Modal>
      )}
    </div>
  )
}
