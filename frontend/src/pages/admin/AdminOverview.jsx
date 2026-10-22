import React, { useEffect, useState } from 'react'
import { NavLink, Outlet } from 'react-router-dom'
import { adminApi } from '../../services/endpoints'
import { apiErrorMessage } from '../../services/api'
import { formatNaira } from '../../utils/format'
import { StatCard, Loader, Alert } from '../../components/UI.jsx'

const tabClass = ({ isActive }) =>
  `px-3 py-2 rounded-lg text-sm font-medium whitespace-nowrap min-h-[40px] flex items-center ${isActive ? 'bg-ink-700 text-gold-400' : 'text-slate-400 hover:text-white'}`

export function AdminLayout() {
  return (
    <div className="max-w-6xl mx-auto px-4 sm:px-6 py-6 sm:py-10">
      <h1 className="font-display text-2xl sm:text-3xl text-white mb-1">Admin</h1>
      <p className="text-slate-400 text-sm mb-6">Users and identity checks, transactions, fraud, claims and the audit trail.</p>
      <div className="relative mb-6 -mx-4 sm:mx-0">
        <nav className="flex gap-1 border-b border-ink-700 pb-2 overflow-x-auto px-4 sm:px-0 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden" aria-label="Admin sections">
          <NavLink to="/admin" end className={tabClass}>Overview</NavLink>
          <NavLink to="/admin/users" className={tabClass}>Users &amp; KYC</NavLink>
          <NavLink to="/admin/transactions" className={tabClass}>Transactions</NavLink>
          <NavLink to="/admin/fraud" className={tabClass}>Fraud flags</NavLink>
          <NavLink to="/admin/claims" className={tabClass}>Claims</NavLink>
          <NavLink to="/admin/audit" className={tabClass}>Audit log</NavLink>
          <NavLink to="/admin/copilot" className={tabClass}>AI copilot</NavLink>
          <NavLink to="/admin/config" className={tabClass}>Config</NavLink>
        </nav>
        <div className="pointer-events-none absolute right-0 top-0 bottom-2 w-8 bg-gradient-to-l from-ink-950 to-transparent sm:hidden" aria-hidden="true" />
      </div>
      <Outlet />
    </div>
  )
}

export default function AdminOverview() {
  const [stats, setStats] = useState(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let mounted = true
    adminApi.stats()
      .then(({ data }) => mounted && setStats(data))
      .catch((err) => mounted && setError(apiErrorMessage(err)))
      .finally(() => mounted && setLoading(false))
    return () => { mounted = false }
  }, [])

  if (loading) return <Loader />

  return (
    <div>
      <Alert type="error">{error}</Alert>
      {stats && (
        <div className="grid grid-cols-2 lg:grid-cols-3 gap-3 sm:gap-4">
          <StatCard label="Total users" value={stats.total_users} />
          <StatCard label="Active users" value={stats.active_users} accent="teal" />
          <StatCard label="Frozen users" value={stats.frozen_users} accent="red" />
          <StatCard label="Total wallet balance" value={formatNaira(stats.total_wallet_balance)} />
          <StatCard label="Reward pool liability" value={formatNaira(stats.total_reward_pool_liability)} accent="teal" />
          <StatCard label="Insurance pool liability" value={formatNaira(stats.total_insurance_pool_liability)} accent="teal" />
          <StatCard label="Platform revenue" value={formatNaira(stats.platform_revenue_balance)} />
          <StatCard label="Transactions total" value={stats.total_transactions} />
          <StatCard label="Transactions today" value={stats.transactions_today} />
          <StatCard label="Open fraud flags" value={stats.open_fraud_flags} accent="red" />
          <StatCard label="Pending claims" value={stats.pending_claims} accent="red" />
        </div>
      )}
    </div>
  )
}
