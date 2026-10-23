import React from 'react'
import { formatNaira, formatDate, statusColor, typeLabel, kycColor, kycLabel } from '../utils/format'
import { profileApi, adminApi } from '../services/endpoints'

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

function initials(name) {
  const parts = String(name || '?').trim().split(/\s+/).slice(0, 2)
  return parts.map((p) => p[0]?.toUpperCase() || '').join('') || '?'
}

/** Profile picture. Photos are private, so they are fetched with the login token and shown from a blob URL. */
export function Avatar({ name, has, userId, version = 0, size = 40, className = '' }) {
  const [url, setUrl] = React.useState(null)
  React.useEffect(() => {
    if (!has) { setUrl(null); return undefined }
    let alive = true, objectUrl = null
    ;(userId ? adminApi.userPhoto(userId) : profileApi.photo())
      .then(({ data }) => { if (alive) { objectUrl = URL.createObjectURL(data); setUrl(objectUrl) } })
      .catch(() => alive && setUrl(null))
    return () => { alive = false; if (objectUrl) URL.revokeObjectURL(objectUrl) }
  }, [has, userId, version])
  const style = { width: size, height: size, fontSize: Math.max(12, size * 0.38) }
  return url
    ? <img src={url} alt={name ? `${name}'s photo` : 'Profile photo'} style={style} className={`rounded-full object-cover bg-ink-700 shrink-0 ${className}`} />
    : <span style={style} aria-hidden="true" className={`rounded-full bg-gold-500/15 border border-gold-500/40 text-gold-400 font-display font-semibold flex items-center justify-center shrink-0 ${className}`}>{initials(name)}</span>
}

export function ProgressBar({ value, max, label, danger }) {
  const pct = max ? Math.min(100, Math.round((value / max) * 100)) : 0
  return (
    <div role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100} aria-label={label}>
      <div className="h-2 rounded-full bg-ink-700 overflow-hidden">
        <div className={`h-full rounded-full ${danger || pct >= 90 ? 'bg-red-400' : 'bg-teal-400'}`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  )
}

const ICONS = {
  user: 'M12 12a4 4 0 100-8 4 4 0 000 8zm-7 8a7 7 0 0114 0',
  level: 'M12 3l8 4v5c0 4.5-3.2 7.8-8 9-4.8-1.2-8-4.5-8-9V7l8-4zm-3 9l2 2 4-4',
  loan: 'M12 3v18M16.5 7.5C16.5 6 14.5 5 12 5s-4.5 1-4.5 2.8c0 4.2 9 2.4 9 6.7 0 1.9-2 3-4.5 3s-4.5-1.2-4.5-3',
  bank: 'M3 10l9-6 9 6M5 10v8m4-8v8m6-8v8m4-8v8M3 20h18',
  device: 'M8 3h8a1 1 0 011 1v16a1 1 0 01-1 1H8a1 1 0 01-1-1V4a1 1 0 011-1zm4 15h.01',
  spark: 'M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8L12 3z',
  chat: 'M4 5h16v11H9l-5 4V5z',
  history: 'M12 7v5l3 2M3 12a9 9 0 109-9 9 9 0 00-6.4 2.6L3 8M3 3v5h5',
  chevron: 'M9 6l6 6-6 6',
}

export function Icon({ name, size = 20, className = '' }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden="true">
      <path d={ICONS[name] || ICONS.user} />
    </svg>
  )
}
