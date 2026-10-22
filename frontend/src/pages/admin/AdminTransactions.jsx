import React, { useCallback, useEffect, useState } from 'react'
import { adminApi } from '../../services/endpoints'
import { apiErrorMessage } from '../../services/api'
import { formatNaira, formatDate, statusColor, typeLabel, formatAccountNumber } from '../../utils/format'
import { Loader, Alert } from '../../components/UI.jsx'

const PAGE = 20
const STATUSES = ['', 'completed', 'pending', 'processing', 'failed', 'flagged', 'reversed']
const TYPES = ['', 'deposit', 'transfer', 'withdrawal', 'insurance_claim_payout']

export default function AdminTransactions() {
  const [items, setItems] = useState([])
  const [q, setQ] = useState('')
  const [query, setQuery] = useState('')
  const [status, setStatus] = useState('')
  const [type, setType] = useState('')
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    setLoading(true); setError('')
    try {
      const { data } = await adminApi.transactions({ q: query || undefined, status: status || undefined, type: type || undefined, page, page_size: PAGE })
      setItems(data)
    } catch (err) { setError(apiErrorMessage(err)) } finally { setLoading(false) }
  }, [query, status, type, page])
  useEffect(() => { load() }, [load])

  return (
    <div>
      <Alert type="error">{error}</Alert>
      <form onSubmit={(e) => { e.preventDefault(); setPage(1); setQuery(q.trim()) }} className="grid grid-cols-2 sm:grid-cols-[1fr_auto_auto_auto] gap-2 mb-4">
        <input className="zp-input col-span-2 sm:col-span-1" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Reference, username, account number or email" aria-label="Search transactions" />
        <select className="zp-input" value={status} onChange={(e) => { setStatus(e.target.value); setPage(1) }} aria-label="Status">
          {STATUSES.map((s) => <option key={s} value={s}>{s ? s : 'Any status'}</option>)}
        </select>
        <select className="zp-input" value={type} onChange={(e) => { setType(e.target.value); setPage(1) }} aria-label="Type">
          {TYPES.map((t) => <option key={t} value={t}>{t ? typeLabel(t) : 'Any type'}</option>)}
        </select>
        <button className="zp-btn-secondary min-h-[48px] col-span-2 sm:col-span-1">Search</button>
      </form>

      {loading ? <Loader /> : (
        <div className="zp-card divide-y divide-ink-700/60">
          {items.length === 0 && <p className="text-sm text-slate-500 p-8 text-center">No transactions match.</p>}
          {items.map((t) => (
            <div key={t.id} className="p-4">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="text-sm text-slate-100">{typeLabel(t.type)} <span className={`zp-pill ml-1 ${statusColor(t.status)}`}>{t.status}</span></p>
                  <p className="text-xs text-slate-500 font-mono break-all mt-1">{t.reference}</p>
                  <p className="text-xs text-slate-400 mt-1">
                    {t.from_username ? `@${t.from_username}` : t.from_name || 'System'}
                    {t.from_account_number ? ` · ${formatAccountNumber(t.from_account_number)}` : ''}
                  </p>
                  {t.narration && <p className="text-xs text-slate-500 mt-0.5 break-words">{t.narration}</p>}
                </div>
                <div className="text-right shrink-0">
                  <p className="zp-amount text-sm font-semibold text-slate-100">{formatNaira(t.amount)}</p>
                  {t.fee_amount > 0 && <p className="text-xs text-slate-500">fee {formatNaira(t.fee_amount)}</p>}
                  <p className="text-xs text-slate-500 mt-1">{formatDate(t.created_at)}</p>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
      <div className="flex items-center justify-between pt-4">
        <button disabled={page <= 1} onClick={() => setPage((p) => p - 1)} className="zp-btn-ghost text-sm disabled:opacity-30">← Previous</button>
        <span className="text-xs text-slate-500">Page {page}</span>
        <button disabled={items.length < PAGE} onClick={() => setPage((p) => p + 1)} className="zp-btn-ghost text-sm disabled:opacity-30">Next →</button>
      </div>
    </div>
  )
}
