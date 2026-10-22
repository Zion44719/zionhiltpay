import React, { useEffect, useState } from 'react'
import { agentApi } from '../services/endpoints'
import { apiErrorMessage } from '../services/api'
import { formatNaira, typeLabel } from '../utils/format'
import { StatCard, Loader, Alert } from '../components/UI.jsx'

const RANGES = [7, 30, 90]

export default function Insights() {
  const [days, setDays] = useState(30)
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    let mounted = true
    setLoading(true)
    setError('')
    agentApi.insights(days)
      .then(({ data }) => mounted && setData(data))
      .catch((err) => mounted && setError(err?.response?.status === 429
        ? 'Too many requests — please wait a moment.' : apiErrorMessage(err)))
      .finally(() => mounted && setLoading(false))
    return () => { mounted = false }
  }, [days])

  const s = data?.summary
  const types = s ? Object.entries(s.by_type) : []

  return (
    <div className="max-w-3xl mx-auto px-4 sm:px-6 py-10">
      <h1 className="font-display text-2xl sm:text-3xl text-white mb-1">Insights</h1>
      <p className="text-slate-400 text-sm mb-6">What you did, what it cost, and what came back to you.</p>

      <div className="flex gap-2 mb-6">
        {RANGES.map((r) => (
          <button key={r} onClick={() => setDays(r)}
            className={`zp-pill ${days === r ? 'text-gold-400 border-gold-500/40 bg-gold-500/10' : 'text-slate-400 border-ink-600'}`}>
            Last {r} days
          </button>
        ))}
      </div>

      <Alert type="error">{error}</Alert>
      {loading ? <Loader label="Crunching your numbers…" /> : s && (
        <>
          <div className="grid sm:grid-cols-3 gap-4 mb-6">
            <StatCard label="Fees paid" value={formatNaira(s.total_fees_paid)} accent="gold" />
            <StatCard label="Cashback earned" value={formatNaira(s.total_rewards_earned)} accent="teal" />
            <StatCard label="Insurance accrued" value={formatNaira(s.total_insurance_accrued)} accent="teal" />
          </div>

          <div className="zp-card p-5 mb-6">
            <p className="text-xs uppercase tracking-wider text-slate-400 mb-2">AI summary</p>
            {data.narrative
              ? <p className="text-sm text-slate-200 leading-relaxed whitespace-pre-wrap">{data.narrative}</p>
              : <p className="text-sm text-slate-500">The written summary isn't available right now — the numbers above and below are still accurate.</p>}
          </div>

          <div className="zp-card p-5">
            <h2 className="font-display text-lg text-white mb-3">Breakdown</h2>
            {types.length === 0 && s.received_transfers.count === 0 && (
              <p className="text-sm text-slate-500">No completed activity in this period.</p>
            )}
            {types.map(([type, v]) => (
              <div key={type} className="flex items-center justify-between py-2.5 border-b border-ink-700/60 last:border-0">
                <span className="text-sm text-slate-200">{typeLabel(type)} <span className="text-slate-500">× {v.count}</span></span>
                <span className="zp-amount text-sm text-slate-100">{formatNaira(v.total_amount)}</span>
              </div>
            ))}
            {s.received_transfers.count > 0 && (
              <div className="flex items-center justify-between py-2.5">
                <span className="text-sm text-slate-200">Transfers received <span className="text-slate-500">× {s.received_transfers.count}</span></span>
                <span className="zp-amount text-sm text-teal-300">{formatNaira(s.received_transfers.total_amount)}</span>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  )
}
