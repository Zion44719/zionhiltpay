import React, { useEffect, useState } from 'react'
import { adminApi } from '../../services/endpoints'
import { apiErrorMessage } from '../../services/api'
import { formatDate } from '../../utils/format'
import { Loader, Alert } from '../../components/UI.jsx'

const PAGE = 30
const sensitive = (a) => /FREEZE|KYC|FRAUD|CONFIG|CLAIM|BLOCKED|LOCKED/.test(a)

export default function AdminAudit() {
  const [logs, setLogs] = useState([])
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    setLoading(true); setError('')
    adminApi.auditLogs(page, PAGE).then(({ data }) => setLogs(data)).catch((e) => setError(apiErrorMessage(e))).finally(() => setLoading(false))
  }, [page])

  return (
    <div>
      <p className="text-xs text-slate-500 mb-4">Append-only record of sensitive actions. Newest first. ID numbers are never written here.</p>
      <Alert type="error">{error}</Alert>
      {loading ? <Loader /> : (
        <div className="zp-card divide-y divide-ink-700/60">
          {logs.length === 0 && <p className="text-sm text-slate-500 p-8 text-center">Nothing logged yet.</p>}
          {logs.map((l) => (
            <div key={l.id} className="p-4">
              <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1">
                <p className={`text-sm font-mono ${sensitive(l.action) ? 'text-gold-400' : 'text-slate-200'}`}>{l.action}</p>
                <p className="text-xs text-slate-500">{formatDate(l.created_at)}</p>
              </div>
              <p className="text-xs text-slate-500 mt-1 break-all">
                {l.actor_role || 'system'} {l.actor_user_id ? `· ${l.actor_user_id.slice(0, 8)}…` : ''}
                {l.entity_type ? ` → ${l.entity_type}${l.entity_id ? ' ' + l.entity_id.slice(0, 8) + '…' : ''}` : ''}
                {l.ip_address ? ` · ${l.ip_address}` : ''}
              </p>
              {l.details && Object.keys(l.details).length > 0 && (
                <pre className="text-xs text-slate-500 mt-1 whitespace-pre-wrap break-words">{JSON.stringify(l.details)}</pre>
              )}
            </div>
          ))}
        </div>
      )}
      <div className="flex items-center justify-between pt-4">
        <button disabled={page <= 1} onClick={() => setPage((p) => p - 1)} className="zp-btn-ghost text-sm disabled:opacity-30">← Previous</button>
        <span className="text-xs text-slate-500">Page {page}</span>
        <button disabled={logs.length < PAGE} onClick={() => setPage((p) => p + 1)} className="zp-btn-ghost text-sm disabled:opacity-30">Next →</button>
      </div>
    </div>
  )
}
