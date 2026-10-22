import React, { useEffect, useState } from 'react'
import { walletApi } from '../services/endpoints'
import { apiErrorMessage } from '../services/api'
import { TransactionRow, Loader, Alert } from '../components/UI.jsx'

export default function Transactions() {
  const [items, setItems] = useState([])
  const [page, setPage] = useState(1)
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const pageSize = 15

  useEffect(() => {
    let mounted = true
    async function load() {
      setLoading(true)
      setError('')
      try {
        const { data } = await walletApi.transactions(page, pageSize)
        if (!mounted) return
        setItems(data.items)
        setTotal(data.total)
      } catch (err) {
        if (mounted) setError(apiErrorMessage(err))
      } finally {
        if (mounted) setLoading(false)
      }
    }
    load()
    return () => { mounted = false }
  }, [page])

  const totalPages = Math.max(1, Math.ceil(total / pageSize))

  return (
    <div className="max-w-3xl mx-auto px-4 sm:px-6 py-10">
      <h1 className="font-display text-2xl sm:text-3xl text-white mb-1">Transaction history</h1>
      <p className="text-slate-400 text-sm mb-8">Every deposit, transfer, withdrawal, reward, and insurance movement on your account.</p>

      <Alert type="error">{error}</Alert>

      <div className="zp-card p-5 sm:p-6">
        {loading ? (
          <Loader />
        ) : items.length === 0 ? (
          <p className="text-sm text-slate-500 py-8 text-center">No transactions yet.</p>
        ) : (
          <>
            {items.map((t) => <TransactionRow key={t.id} txn={t} />)}
            <div className="flex items-center justify-between mt-5 pt-4 border-t border-ink-700">
              <button disabled={page <= 1} onClick={() => setPage((p) => p - 1)} className="zp-btn-ghost text-sm disabled:opacity-30">← Previous</button>
              <span className="text-xs text-slate-500">Page {page} of {totalPages}</span>
              <button disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)} className="zp-btn-ghost text-sm disabled:opacity-30">Next →</button>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
