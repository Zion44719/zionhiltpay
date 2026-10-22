import React from 'react'
import { formatNaira, formatDate, statusColor, typeLabel, kycColor, kycLabel } from '../utils/format'

export function StatCard({ label, value, accent = 'gold', sub }) {
  const accentClass = accent === 'teal' ? 'text-teal-300' : accent === 'red' ? 'text-red-300' : 'text-gold-400'
  return (
    <div className="zp-card p-4 sm:p-5 min-w-0">
      <p className="text-xs uppercase tracking-wider text-slate-400 mb-2 truncate">{label}</p>
      <p className={`zp-amount text-lg sm:text-2xl font-semibold [overflow-wrap:anywhere] ${accentClass}`}>{value}</p>
      {sub && <p className="text-xs text-slate-500 mt-1">{sub}</p>}
    </div>
  )
}

export function Alert({ type = 'error', children }) {
  if (!children) return null
  const styles = {
    error: 'bg-red-500/10 border-red-500/40 text-red-300',
    success: 'bg-teal-500/10 border-teal-500/40 text-teal-300',
    info: 'bg-gold-500/10 border-gold-500/40 text-gold-400',
  }
  return (
    <div className={`border rounded-lg px-4 py-3 text-sm mb-4 ${styles[type]}`}>
      {children}
    </div>
  )
}

export function TransactionRow({ txn, currentUserId }) {
  const isOutgoing = txn.type === 'withdrawal' || (txn.type === 'transfer')
  const sign = txn.type === 'deposit' || txn.type === 'reward_credit' || txn.type === 'insurance_claim_payout' ? '+' : '−'
  const colorClass = sign === '+' ? 'text-teal-300' : 'text-slate-200'

  return (
    <div className="flex items-center justify-between py-3.5 px-1 border-b border-ink-700/60 last:border-0">
      <div className="flex items-center gap-3 min-w-0">
        <div className="w-9 h-9 rounded-full bg-ink-700 flex items-center justify-center text-xs font-mono text-slate-400 shrink-0">
          {txn.type.slice(0, 2).toUpperCase()}
        </div>
        <div className="min-w-0">
          <p className="text-sm text-slate-100 truncate">{txn.narration || typeLabel(txn.type)}</p>
          <p className="text-xs text-slate-500 font-mono">{txn.reference} · {formatDate(txn.created_at)}</p>
        </div>
      </div>
      <div className="text-right shrink-0 pl-3">
        <p className={`zp-amount text-sm font-semibold ${colorClass}`}>{sign} {formatNaira(txn.amount)}</p>
        <span className={`zp-pill mt-1 inline-block ${statusColor(txn.status)}`}>{txn.status}</span>
      </div>
    </div>
  )
}

export function Loader({ label = 'Loading…' }) {
  return (
    <div className="flex items-center gap-3 text-slate-400 py-10 justify-center">
      <div className="w-4 h-4 rounded-full border-2 border-gold-500 border-t-transparent animate-spin" />
      <span className="text-sm">{label}</span>
    </div>
  )
}

export function KycBadge({ status }) {
  return <span className={`zp-pill whitespace-nowrap ${kycColor(status)}`}>{kycLabel(status)}</span>
}

/** Copies text; works on plain-http pages too (navigator.clipboard needs a secure context). */
export function CopyButton({ text, label = 'Copy', className = '' }) {
  const [done, setDone] = React.useState(false)
  const copy = async () => {
    try {
      if (navigator.clipboard && window.isSecureContext) await navigator.clipboard.writeText(text)
      else {
        const ta = document.createElement('textarea')
        ta.value = text; ta.style.position = 'fixed'; ta.style.opacity = '0'
        document.body.appendChild(ta); ta.select(); document.execCommand('copy'); document.body.removeChild(ta)
      }
      setDone(true); setTimeout(() => setDone(false), 1600)
    } catch { /* clipboard blocked: nothing useful to do */ }
  }
  return (
    <button type="button" onClick={copy} className={`zp-btn-secondary !px-4 !py-2 text-sm min-h-[40px] ${className}`}>
      {done ? 'Copied ✓' : label}
    </button>
  )
}
