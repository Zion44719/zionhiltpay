export function formatNaira(amount) {
  const n = Number(amount || 0)
  return new Intl.NumberFormat('en-NG', {
    style: 'currency',
    currency: 'NGN',
    minimumFractionDigits: 2,
  }).format(n)
}

export function formatDate(isoString) {
  if (!isoString) return '—'
  const d = new Date(isoString)
  return d.toLocaleString('en-NG', {
    day: '2-digit', month: 'short', year: 'numeric',
    hour: '2-digit', minute: '2-digit',
  })
}

export function statusColor(status) {
  switch (status) {
    case 'completed': return 'text-teal-300 border-teal-500/40 bg-teal-500/10'
    case 'pending':
    case 'processing': return 'text-gold-400 border-gold-500/40 bg-gold-500/10'
    case 'flagged': return 'text-red-300 border-red-500/40 bg-red-500/10'
    case 'failed':
    case 'reversed': return 'text-slate-400 border-slate-500/40 bg-slate-500/10'
    default: return 'text-slate-400 border-slate-500/40 bg-slate-500/10'
  }
}

export function typeLabel(type) {
  return {
    deposit: 'Deposit',
    withdrawal: 'Withdrawal',
    transfer: 'Transfer',
    reward_credit: 'Reward',
    insurance_contribution: 'Insurance Contribution',
    insurance_claim_payout: 'Insurance Payout',
    fee: 'Fee',
    reversal: 'Reversal',
  }[type] || type
}

/** 7009255634 -> "7009 255 634" (grouping only; the stored value has no spaces) */
export function formatAccountNumber(n) {
  if (!n) return '—'
  return String(n).replace(/^(\d{4})(\d{3})(\d{3})$/, '$1 $2 $3')
}

export function kycLabel(status) {
  return { not_submitted: 'No ID on file', submitted: 'Under review', verified: 'Verified', rejected: 'Rejected' }[status] || status
}

export function kycColor(status) {
  switch (status) {
    case 'verified': return 'text-teal-300 border-teal-500/40 bg-teal-500/10'
    case 'submitted': return 'text-gold-400 border-gold-500/40 bg-gold-500/10'
    case 'rejected': return 'text-red-300 border-red-500/40 bg-red-500/10'
    default: return 'text-slate-400 border-slate-500/40 bg-slate-500/10'
  }
}

/** Same rules as the server (backend/app/core/identity.py) so people get feedback before submitting. */
export function normalizePhone(raw) {
  const s = String(raw || '').replace(/[\s\-().]/g, '')
  if (/^0\d{10}$/.test(s)) return '+234' + s.slice(1)
  if (/^234\d{10}$/.test(s)) return '+' + s
  if (/^\+\d{10,15}$/.test(s)) return s
  return null
}
