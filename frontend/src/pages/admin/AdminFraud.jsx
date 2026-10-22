import React, { useEffect, useState } from 'react'
import { adminApi, agentApi } from '../../services/endpoints'
import TriageBox from '../../components/TriageBox.jsx'
import { apiErrorMessage } from '../../services/api'
import { formatDate } from '../../utils/format'
import { Loader, Alert } from '../../components/UI.jsx'

const severityStyle = {
  low: 'text-slate-400 border-slate-500/40 bg-slate-500/10',
  medium: 'text-gold-400 border-gold-500/40 bg-gold-500/10',
  high: 'text-red-300 border-red-500/40 bg-red-500/10',
  critical: 'text-red-200 border-red-400/60 bg-red-500/20',
}

export default function AdminFraud() {
  const [flags, setFlags] = useState([])
  const [showResolved, setShowResolved] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')

  const load = async () => {
    setLoading(true)
    setError('')
    try {
      const { data } = await adminApi.fraudFlags(showResolved ? true : false)
      setFlags(data)
    } catch (err) {
      setError(apiErrorMessage(err))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [showResolved])

  const resolve = async (id) => {
    try {
      await adminApi.resolveFraudFlag(id, 'Reviewed by admin')
      setSuccess('Flag resolved.')
      load()
    } catch (err) {
      setError(apiErrorMessage(err))
    }
  }

  return (
    <div>
      <Alert type="error">{error}</Alert>
      <Alert type="success">{success}</Alert>

      <div className="flex gap-2 mb-5">
        <button onClick={() => setShowResolved(false)} className={`zp-pill ${!showResolved ? 'text-gold-400 border-gold-500/40 bg-gold-500/10' : 'text-slate-400 border-ink-600'}`}>Open</button>
        <button onClick={() => setShowResolved(true)} className={`zp-pill ${showResolved ? 'text-gold-400 border-gold-500/40 bg-gold-500/10' : 'text-slate-400 border-ink-600'}`}>Resolved</button>
      </div>

      {loading ? <Loader /> : (
        <div className="space-y-3">
          {flags.length === 0 && <p className="text-sm text-slate-500 zp-card p-8 text-center">No {showResolved ? 'resolved' : 'open'} flags.</p>}
          {flags.map((f) => (
            <div key={f.id} className="zp-card p-4">
              <div className="flex items-center justify-between mb-2">
                <span className={`zp-pill ${severityStyle[f.severity]}`}>{f.severity}</span>
                <span className="text-xs text-slate-500">{formatDate(f.created_at)}</span>
              </div>
              <p className="text-sm text-slate-100 font-mono mb-1">{f.rule_code}</p>
              <pre className="text-xs text-slate-500 overflow-x-auto whitespace-pre-wrap">{JSON.stringify(f.details, null, 2)}</pre>
              <TriageBox run={() => agentApi.triageFlag(f.id)} />
              {!f.resolved && (
                <button onClick={() => resolve(f.id)} className="zp-btn-secondary !py-1.5 !px-3 text-xs mt-3">Mark resolved</button>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
