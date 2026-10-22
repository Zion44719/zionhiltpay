import React, { useEffect, useState } from 'react'
import { deviceApi, walletApi } from '../services/endpoints'
import { apiErrorMessage } from '../services/api'
import { formatNaira, formatDate } from '../utils/format'
import { Alert, Loader } from '../components/UI.jsx'

const DEVICE_TYPES = ['phone', 'laptop', 'tablet', 'other']
const CLAIM_TYPES = ['lost', 'stolen', 'damaged']

export default function Devices() {
  const [devices, setDevices] = useState([])
  const [claims, setClaims] = useState([])
  const [insuranceBalance, setInsuranceBalance] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')

  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState({ device_type: 'phone', brand: '', model: '', serial_number: '', estimated_value: '' })
  const [submitting, setSubmitting] = useState(false)

  const [claimDeviceId, setClaimDeviceId] = useState(null)
  const [claimType, setClaimType] = useState('lost')
  const [claimDesc, setClaimDesc] = useState('')

  const load = async () => {
    setLoading(true)
    setError('')
    try {
      const [devRes, claimRes, balRes] = await Promise.all([
        deviceApi.list(), deviceApi.myClaims(), walletApi.balance(),
      ])
      setDevices(devRes.data)
      setClaims(claimRes.data)
      setInsuranceBalance(balRes.data.insurance_balance)
    } catch (err) {
      setError(apiErrorMessage(err))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const submitDevice = async (e) => {
    e.preventDefault()
    setSubmitting(true)
    setError('')
    try {
      await deviceApi.register({ ...form, estimated_value: Number(form.estimated_value) })
      setShowForm(false)
      setForm({ device_type: 'phone', brand: '', model: '', serial_number: '', estimated_value: '' })
      setSuccess('Device registered for insurance coverage.')
      await load()
    } catch (err) {
      setError(apiErrorMessage(err))
    } finally {
      setSubmitting(false)
    }
  }

  const submitClaim = async (deviceId) => {
    setSubmitting(true)
    setError('')
    try {
      await deviceApi.fileClaim({ device_id: deviceId, claim_type: claimType, description: claimDesc })
      setClaimDeviceId(null)
      setClaimDesc('')
      setSuccess('Claim submitted for review by our team.')
      await load()
    } catch (err) {
      setError(apiErrorMessage(err))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="max-w-3xl mx-auto px-4 sm:px-6 py-10">
      <h1 className="font-display text-2xl sm:text-3xl text-white mb-1">Devices &amp; Insurance</h1>
      <p className="text-slate-400 text-sm mb-6">
        Register your phone or laptop to start building coverage. A portion of every transaction
        fee you pay accrues into your personal insurance pool below — no separate premium needed.
      </p>

      <div className="zp-card p-5 mb-6 flex items-center justify-between">
        <div>
          <p className="text-xs uppercase tracking-wider text-slate-400 mb-1">Accrued insurance pool</p>
          <p className="zp-amount text-2xl font-semibold text-teal-300">{formatNaira(insuranceBalance)}</p>
        </div>
        <button onClick={() => setShowForm((s) => !s)} className="zp-btn-primary">
          {showForm ? 'Cancel' : '+ Register device'}
        </button>
      </div>

      <Alert type="error">{error}</Alert>
      <Alert type="success">{success}</Alert>

      {showForm && (
        <form onSubmit={submitDevice} className="zp-card p-6 space-y-4 mb-6">
          <div>
            <label className="zp-label">Device type</label>
            <div className="grid grid-cols-4 gap-2">
              {DEVICE_TYPES.map((t) => (
                <button
                  type="button" key={t}
                  onClick={() => setForm({ ...form, device_type: t })}
                  className={`rounded-lg px-3 py-2 text-sm border capitalize transition-colors ${
                    form.device_type === t ? 'border-gold-500 bg-gold-500/10 text-gold-400' : 'border-ink-600 text-slate-400'
                  }`}
                >{t}</button>
              ))}
            </div>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="zp-label">Brand</label>
              <input className="zp-input" value={form.brand} onChange={(e) => setForm({ ...form, brand: e.target.value })} placeholder="Apple, Samsung…" />
            </div>
            <div>
              <label className="zp-label">Model</label>
              <input className="zp-input" value={form.model} onChange={(e) => setForm({ ...form, model: e.target.value })} placeholder="iPhone 15" />
            </div>
          </div>
          <div>
            <label className="zp-label">Serial number (optional)</label>
            <input className="zp-input font-mono" value={form.serial_number} onChange={(e) => setForm({ ...form, serial_number: e.target.value })} />
          </div>
          <div>
            <label className="zp-label">Estimated value (₦)</label>
            <input className="zp-input zp-amount" required type="number" min="1" value={form.estimated_value} onChange={(e) => setForm({ ...form, estimated_value: e.target.value })} placeholder="0.00" />
          </div>
          <button type="submit" disabled={submitting} className="zp-btn-primary w-full">
            {submitting ? 'Registering…' : 'Register device'}
          </button>
        </form>
      )}

      {loading ? <Loader /> : (
        <>
          <h2 className="font-display text-lg text-white mb-3">Your devices</h2>
          <div className="space-y-3 mb-10">
            {devices.length === 0 && <p className="text-sm text-slate-500 zp-card p-6 text-center">No devices registered yet.</p>}
            {devices.map((d) => (
              <div key={d.id} className="zp-card p-5">
                <div className="flex items-center justify-between mb-3">
                  <div>
                    <p className="text-slate-100 font-medium capitalize">{d.brand} {d.model} <span className="text-slate-500 text-xs">({d.device_type})</span></p>
                    <p className="text-xs text-slate-500">Registered {formatDate(d.registered_at)} · Estimated value {formatNaira(d.estimated_value)}</p>
                  </div>
                  <span className={`zp-pill ${d.status === 'active' ? 'text-teal-300 border-teal-500/40 bg-teal-500/10' : 'text-gold-400 border-gold-500/40 bg-gold-500/10'}`}>
                    {d.status}
                  </span>
                </div>
                {d.status === 'active' && (
                  claimDeviceId === d.id ? (
                    <div className="border-t border-ink-700 pt-3 mt-3 space-y-3">
                      <div className="grid grid-cols-3 gap-2">
                        {CLAIM_TYPES.map((c) => (
                          <button key={c} type="button" onClick={() => setClaimType(c)}
                            className={`rounded-lg px-3 py-2 text-xs border capitalize ${claimType === c ? 'border-gold-500 bg-gold-500/10 text-gold-400' : 'border-ink-600 text-slate-400'}`}>
                            {c}
                          </button>
                        ))}
                      </div>
                      <textarea className="zp-input text-sm" rows={2} placeholder="What happened?" value={claimDesc} onChange={(e) => setClaimDesc(e.target.value)} />
                      <div className="flex gap-2">
                        <button onClick={() => setClaimDeviceId(null)} className="zp-btn-secondary flex-1 !py-2 text-sm">Cancel</button>
                        <button onClick={() => submitClaim(d.id)} disabled={submitting} className="zp-btn-primary flex-1 !py-2 text-sm">Submit claim</button>
                      </div>
                    </div>
                  ) : (
                    <button onClick={() => setClaimDeviceId(d.id)} className="text-sm text-gold-400 hover:underline">File a claim →</button>
                  )
                )}
              </div>
            ))}
          </div>

          <h2 className="font-display text-lg text-white mb-3">Your claims</h2>
          <div className="space-y-3">
            {claims.length === 0 && <p className="text-sm text-slate-500 zp-card p-6 text-center">No claims filed.</p>}
            {claims.map((c) => (
              <div key={c.id} className="zp-card p-4 flex items-center justify-between">
                <div>
                  <p className="text-sm text-slate-100 capitalize">{c.claim_type} · Requested {formatNaira(c.requested_amount)}</p>
                  <p className="text-xs text-slate-500">{formatDate(c.created_at)}</p>
                </div>
                <span className="zp-pill text-slate-300 border-slate-500/40 bg-slate-500/10 capitalize">{c.status}</span>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  )
}
