import React, { useCallback, useEffect, useState } from 'react'
import { adminApi } from '../../services/endpoints'
import { apiErrorMessage } from '../../services/api'
import { formatNaira, formatDate, formatAccountNumber } from '../../utils/format'
import { Loader, Alert } from '../../components/UI.jsx'

const PAGE = 20
const FILTERS = [['', 'All'], ['active', 'Active'], ['repaid', 'Repaid']]

export default function AdminLoans() {
  const [status, setStatus] = useState('active')
  const [page, setPage] = useState(1)
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    setLoading(true); setError('')
    try { const { data } = await adminApi.loans({ status: status || undefined, page, page_size: PAGE }); setRows(data) } catch (e) { setError(apiErrorMessage(e)) } finally { setLoading(false) }
  }, [status, page])
  useEffect(() => { load() }, [load])

  return (
    <div>
      <Alert type="error">{error}</Alert>
      <div className="flex gap-2 mb-4" role="group" aria-label="Filter loans">
        {FILTERS.map(([v, label]) => (
          <button key={v} onClick={() => { setStatus(v); setPage(1) }} aria-pressed={status === v}
            className={`zp-pill whitespace-nowrap min-h-[36px] px-4 ${status === v ? 'text-gold-400 border-gold-500/40 bg-gold-500/10' : 'text-slate-400 border-ink-600'}`}>{label}</button>
        ))}
      </div>
      {loading ? <Loader /> : (
        <div className="zp-card divide-y divide-ink-700/60">
          {rows.length === 0 && <p className="text-sm text-slate-500 p-8 text-center">No loans.</p>}
          {rows.map((l) => (
            <div key={l.id} className="p-4">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="text-sm text-slate-100 break-words">{l.user.full_name} <span className="text-xs text-slate-500">{l.user.username ? `@${l.user.username}` : ''}</span></p>
                  <p className="text-xs text-slate-500">{formatAccountNumber(l.user.account_number)}</p>
                  <p className="text-xs text-slate-500 font-mono break-all mt-1">{l.reference}</p>
                </div>
                <span className={`zp-pill shrink-0 ${l.status === 'repaid' ? 'text-teal-300 border-teal-500/40 bg-teal-500/10' : l.is_overdue ? 'text-red-300 border-red-500/40 bg-red-500/10' : 'text-gold-400 border-gold-500/40 bg-gold-500/10'}`}>{l.status === 'repaid' ? 'Repaid' : l.is_overdue ? 'Overdue' : 'Active'}</span>
              </div>
              <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs text-slate-400 mt-3">
                <div><dt className="text-slate-500">Borrowed</dt><dd className="zp-amount text-slate-200">{formatNaira(l.principal)}</dd></div>
                <div><dt className="text-slate-500">Owes now</dt><dd className="zp-amount text-slate-200">{formatNaira(l.outstanding)}</dd></div>
                <div><dt className="text-slate-500">Taken</dt><dd>{formatDate(l.disbursed_at)}</dd></div>
                <div><dt className="text-slate-500">Due</dt><dd className={l.is_overdue ? 'text-red-300' : ''}>{formatDate(l.due_at)}</dd></div>
              </dl>
            </div>
          ))}
        </div>
      )}
      <div className="flex items-center justify-between pt-4">
        <button disabled={page <= 1} onClick={() => setPage((p) => p - 1)} className="zp-btn-ghost text-sm disabled:opacity-30">← Previous</button>
        <span className="text-xs text-slate-500">Page {page}</span>
        <button disabled={rows.length < PAGE} onClick={() => setPage((p) => p + 1)} className="zp-btn-ghost text-sm disabled:opacity-30">Next →</button>
      </div>
    </div>
  )
}
