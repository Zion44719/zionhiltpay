import React, { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { walletApi } from '../services/endpoints'
import { apiErrorMessage } from '../services/api'
import { formatNaira } from '../utils/format'
import { Alert } from '../components/UI.jsx'
import PinPrompt from '../components/PinPrompt.jsx'

export default function Withdraw() {
  const navigate = useNavigate()
  const [amount, setAmount] = useState('')
  const [bankAccount, setBankAccount] = useState('')
  const [bankCode, setBankCode] = useState('')
  const [error, setError] = useState('')
  const [pinOpen, setPinOpen] = useState(false)
  const [pinError, setPinError] = useState('')
  const [loading, setLoading] = useState(false)
  const [success, setSuccess] = useState(null)

  const openConfirm = (e) => {
    e.preventDefault()
    setError('')
    if (!amount || Number(amount) <= 0 || bankAccount.length !== 10 || !bankCode) {
      setError('Enter a valid amount and 10-digit account number.')
      return
    }
    setPinOpen(true)
  }

  const confirmWithdraw = async (pin) => {
    setLoading(true)
    setPinError('')
    try {
      const { data } = await walletApi.withdraw({
        amount: Number(amount),
        pin,
        bank_account_number: bankAccount,
        bank_code: bankCode,
      })
      setPinOpen(false)
      setSuccess(data)
    } catch (err) {
      setPinError(apiErrorMessage(err))
    } finally {
      setLoading(false)
    }
  }

  if (success) {
    return (
      <div className="max-w-md mx-auto px-4 sm:px-6 py-16 text-center">
        <div className="w-14 h-14 rounded-full bg-teal-500/15 border border-teal-500/40 text-teal-300 flex items-center justify-center mx-auto mb-5 text-2xl">✓</div>
        <h1 className="font-display text-2xl text-white mb-2">Withdrawal initiated</h1>
        <p className="text-slate-400 text-sm mb-1">{formatNaira(success.amount)} is on its way to your bank account.</p>
        <p className="text-slate-500 text-xs font-mono mb-8">{success.reference}</p>
        <button onClick={() => navigate('/dashboard')} className="zp-btn-primary">Back to dashboard</button>
      </div>
    )
  }

  return (
    <div className="max-w-md mx-auto px-4 sm:px-6 py-16">
      <h1 className="font-display text-3xl text-white mb-2">Withdraw to bank</h1>
      <p className="text-slate-400 text-sm mb-8">A flat withdrawal fee applies; a share still returns to you as rewards and insurance coverage.</p>

      <Alert type="error">{error}</Alert>

      <form onSubmit={openConfirm} className="zp-card p-6 space-y-4">
        <div>
          <label className="zp-label">Amount (₦)</label>
          <input className="zp-input zp-amount" required type="number" min="1" step="0.01" value={amount} onChange={(e) => setAmount(e.target.value)} placeholder="0.00" />
        </div>
        <div>
          <label className="zp-label">Bank account number (NUBAN)</label>
          <input className="zp-input font-mono" required maxLength={10} value={bankAccount} onChange={(e) => setBankAccount(e.target.value.replace(/\D/g, ''))} placeholder="0123456789" />
        </div>
        <div>
          <label className="zp-label">Bank code</label>
          <input className="zp-input font-mono" required value={bankCode} onChange={(e) => setBankCode(e.target.value)} placeholder="e.g. 058" />
        </div>
        <button type="submit" className="zp-btn-primary w-full">Review withdrawal</button>
      </form>

      <PinPrompt
        open={pinOpen}
        onCancel={() => { setPinOpen(false); setPinError('') }}
        onConfirm={confirmWithdraw}
        loading={loading}
        error={pinError}
      />
    </div>
  )
}
