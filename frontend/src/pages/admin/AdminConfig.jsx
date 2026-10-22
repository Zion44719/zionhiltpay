import React, { useEffect, useState } from 'react'
import { adminApi } from '../../services/endpoints'
import { apiErrorMessage } from '../../services/api'
import { Loader, Alert } from '../../components/UI.jsx'

const FIELDS = [
  { key: 'reward_rate', label: 'Reward rate (fraction of amount)', step: '0.0001' },
  { key: 'insurance_contribution_rate', label: 'Insurance contribution rate (fraction of fee)', step: '0.0001' },
  { key: 'transaction_fee_rate', label: 'Transfer fee rate (fraction of amount)', step: '0.0001' },
  { key: 'withdrawal_fee_flat', label: 'Withdrawal flat fee (₦)', step: '0.01' },
  { key: 'fraud_velocity_window_minutes', label: 'Fraud velocity window (minutes)', step: '1' },
  { key: 'fraud_velocity_max_txns', label: 'Fraud velocity max transactions', step: '1' },
  { key: 'fraud_large_amount_threshold', label: 'Large-amount fraud threshold (₦)', step: '0.01' },
]

export default function AdminConfig() {
  const [config, setConfig] = useState(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')

  useEffect(() => {
    adminApi.getConfig()
      .then(({ data }) => setConfig(data))
      .catch((err) => setError(apiErrorMessage(err)))
      .finally(() => setLoading(false))
  }, [])

  const update = (key) => (e) => setConfig({ ...config, [key]: e.target.value })

  const save = async (e) => {
    e.preventDefault()
    setSaving(true)
    setError('')
    setSuccess('')
    try {
      const payload = {}
      FIELDS.forEach(({ key }) => { payload[key] = Number(config[key]) })
      const { data } = await adminApi.updateConfig(payload)
      setConfig(data)
      setSuccess('Platform configuration updated.')
    } catch (err) {
      setError(apiErrorMessage(err) + ' (super_admin role required to change config)')
    } finally {
      setSaving(false)
    }
  }

  if (loading) return <Loader />

  return (
    <div className="max-w-xl">
      <Alert type="error">{error}</Alert>
      <Alert type="success">{success}</Alert>
      {config && (
        <form onSubmit={save} className="zp-card p-6 space-y-4">
          {FIELDS.map(({ key, label, step }) => (
            <div key={key}>
              <label className="zp-label">{label}</label>
              <input className="zp-input zp-amount" type="number" step={step} value={config[key]} onChange={update(key)} />
            </div>
          ))}
          <button type="submit" disabled={saving} className="zp-btn-primary w-full">
            {saving ? 'Saving…' : 'Save configuration'}
          </button>
        </form>
      )}
    </div>
  )
}
