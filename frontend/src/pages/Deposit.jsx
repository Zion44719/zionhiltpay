import React, { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { walletApi } from '../services/endpoints'
import { apiErrorMessage } from '../services/api'
import { formatNaira } from '../utils/format'
import { Alert } from '../components/UI.jsx'

export default function Deposit() {
  const navigate = useNavigate()
  const [amount, setAmount] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [success, setSuccess] = useState(null)

  const submit = async (e) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const { data } = await walletApi.deposit({ amount: Number(amount), narration: 'Wallet funding' })
      setSuccess(data)
    } catch (err) {
      setError(apiErrorMessage(err))
    } finally {
      setLoading(false)
    }
  }

  if (success) {
    return (
      <div className="max-w-md mx-auto px-4 sm:px-6 py-16 text-center">
        <div className="w-14 h-14 rounded-full bg-teal-500/15 border border-teal-500/40 text-teal-300 flex items-center justify-center mx-auto mb-5 text-2xl">✓</div>
        <h1 className="font-display text-2xl text-white mb-2">Wallet funded</h1>
        <p className="text-slate-400 text-sm mb-8">{formatNaira(success.amount)} added to your wallet via the payment gateway.</p>
        <button onClick={() => navigate('/dashboard')} className="zp-btn-primary">Back to dashboard</button>
      </div>
    )
  }

  return (
    <div className="max-w-md mx-auto px-4 sm:px-6 py-16">
      <h1 className="font-display text-3xl text-white mb-2">Fund your wallet</h1>
      <p className="text-slate-400 text-sm mb-8">
        Simulated via the ZionhiltPay mock payment gateway — no real card details are collected here.
      </p>

      <Alert type="error">{error}</Alert>

      <form onSubmit={submit} className="zp-card p-6 space-y-4">
        <div>
          <label className="zp-label">Amount (₦)</label>
          <input className="zp-input zp-amount" required type="number" min="1" step="0.01" value={amount} onChange={(e) => setAmount(e.target.value)} placeholder="0.00" />
        </div>
        <button type="submit" disabled={loading} className="zp-btn-primary w-full">
          {loading ? 'Processing…' : 'Fund wallet'}
        </button>
      </form>
    </div>
  )
}
