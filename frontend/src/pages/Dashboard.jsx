import React, { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { walletApi } from '../services/endpoints'
import { apiErrorMessage } from '../services/api'
import { formatNaira, formatAccountNumber } from '../utils/format'
import { StatCard, TransactionRow, Loader, Alert, CopyButton, KycBadge } from '../components/UI.jsx'
import { useAuth } from '../context/AuthContext.jsx'

export default function Dashboard() {
  const { profile } = useAuth()
  const [balance, setBalance] = useState(null)
  const [txns, setTxns] = useState([])
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let mounted = true
    async function load() {
      setLoading(true)
      setError('')
      try {
        const [balRes, txnRes] = await Promise.all([walletApi.balance(), walletApi.transactions(1, 6)])
        if (!mounted) return
        setBalance(balRes.data)
        setTxns(txnRes.data.items)
      } catch (err) {
        if (mounted) setError(apiErrorMessage(err))
      } finally {
        if (mounted) setLoading(false)
      }
    }
    load()
    return () => { mounted = false }
  }, [])

  const accountNumber = balance?.account_number || profile?.account_number
  const kyc = profile?.kyc_status

  return (
    <div className="max-w-6xl mx-auto px-4 sm:px-6 py-6 sm:py-10">
      <h1 className="font-display text-2xl sm:text-3xl text-white mb-1">
        Welcome{profile?.full_name ? `, ${profile.full_name.split(' ')[0]}` : ''}
      </h1>
      <p className="text-slate-400 text-sm mb-5">Here's where things stand today.</p>

      <Alert type="error">{error}</Alert>

      {accountNumber && (
        <section className="zp-card p-4 sm:p-5 mb-4 flex items-center justify-between gap-3" aria-label="Your account number">
          <div className="min-w-0">
            <p className="text-xs uppercase tracking-wider text-slate-400 mb-1">Your account number</p>
            <p className="zp-amount text-xl sm:text-2xl font-semibold text-white tracking-wider">{formatAccountNumber(accountNumber)}</p>
            <p className="text-xs text-slate-500 mt-1 truncate">
              {profile?.username ? `@${profile.username} · ` : ''}Share this to receive money
            </p>
          </div>
          <CopyButton text={accountNumber} className="shrink-0" />
        </section>
      )}

      {kyc && kyc !== 'not_submitted' && (
        <div className="flex items-center gap-2 mb-5 text-xs text-slate-400">
          Identity: <KycBadge status={kyc} />
          {kyc === 'submitted' && <span>We're reviewing your ID. You can keep using your wallet meanwhile.</span>}
          {kyc === 'rejected' && <span className="text-red-300">Your ID could not be verified. Please contact support.</span>}
        </div>
      )}

      {loading ? (
        <Loader label="Loading your wallet…" />
      ) : (
        <>
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 sm:gap-4 mb-5">
            <div className="col-span-2 sm:col-span-1">
              <StatCard label="Wallet balance" value={formatNaira(balance?.wallet_balance)} accent="gold" />
            </div>
            <StatCard label="Rewards" value={formatNaira(balance?.reward_balance)} accent="teal" sub="Cashback earned" />
            <StatCard label="Device cover" value={formatNaira(balance?.insurance_balance)} accent="teal" sub="Builds as you spend" />
          </div>

          <div className="grid grid-cols-2 sm:flex sm:flex-wrap gap-3 mb-8">
            <Link to="/transfer" className="zp-btn-primary min-h-[48px]">Send money</Link>
            <Link to="/deposit" className="zp-btn-secondary min-h-[48px]">Fund wallet</Link>
            <Link to="/withdraw" className="zp-btn-secondary min-h-[48px]">Withdraw</Link>
            <Link to="/devices" className="zp-btn-secondary min-h-[48px]">Devices</Link>
          </div>

          <div className="zp-card p-4 sm:p-6">
            <div className="flex items-center justify-between mb-2">
              <h2 className="font-display text-lg text-white">Recent activity</h2>
              <Link to="/transactions" className="text-sm text-gold-400 hover:underline">View all</Link>
            </div>
            {txns.length === 0 ? (
              <p className="text-sm text-slate-500 py-8 text-center">No transactions yet. Fund your wallet to get started.</p>
            ) : (
              <div>{txns.map((t) => <TransactionRow key={t.id} txn={t} />)}</div>
            )}
          </div>
        </>
      )}
    </div>
  )
}
