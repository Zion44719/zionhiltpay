import React, { useEffect, useState } from 'react'
import { adminApi, agentApi } from '../../services/endpoints'
import TriageBox from '../../components/TriageBox.jsx'
import { apiErrorMessage } from '../../services/api'
import { formatNaira, formatDate } from '../../utils/format'
import { Loader, Alert } from '../../components/UI.jsx'

export default function AdminClaims() {
  const [claims, setClaims] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [reviewing, setReviewing] = useState(null)
  const [approvedAmount, setApprovedAmount] = useState('')

  const load = async () => {
    setLoading(true)
    setError('')
    try {
      const { data } = await adminApi.claims('submitted')
      setClaims(data)
    } catch (err) {
      setError(apiErrorMessage(err))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const approve = async (id) => {
    try {
      await adminApi.reviewClaim(id, {
        approve: true,
        approved_amount: approvedAmount ? Number(approvedAmount) : undefined,
      })
      setSuccess('Claim approved and paid out.')
      setReviewing(null)
      setApprovedAmount('')
      load()
    } catch (err) {
      setError(apiErrorMessage(err))
    }
  }

  const reject = async (id) => {
    try {
      await adminApi.reviewClaim(id, { approve: false, review_note: 'Rejected by admin' })
      setSuccess('Claim rejected.')
      load()
    } catch (err) {
      setError(apiErrorMessage(err))
    }
  }

  return (
    <div>
      <Alert type="error">{error}</Alert>
      <Alert type="success">{success}</Alert>

      {loading ? <Loader /> : (
        <div className="space-y-3">
          {claims.length === 0 && <p className="text-sm text-slate-500 zp-card p-8 text-center">No pending claims.</p>}
          {claims.map((c) => (
            <div key={c.id} className="zp-card p-5">
              <div className="flex items-center justify-between mb-2">
                <p className="text-sm text-slate-100 capitalize">{c.claim_type} claim · Requested {formatNaira(c.requested_amount)}</p>
                <span className="text-xs text-slate-500">{formatDate(c.created_at)}</span>
              </div>
              {c.description && <p className="text-sm text-slate-400 mb-3">{c.description}</p>}

              <div className="mb-3"><TriageBox run={() => agentApi.triageClaim(c.id)} /></div>

              {reviewing === c.id ? (
                <div className="flex items-center gap-2">
                  <input
                    className="zp-input zp-amount flex-1"
                    type="number"
                    placeholder={`Max ${c.requested_amount}`}
                    value={approvedAmount}
                    onChange={(e) => setApprovedAmount(e.target.value)}
                  />
                  <button onClick={() => approve(c.id)} className="zp-btn-primary !px-4 text-sm">Approve &amp; pay</button>
                  <button onClick={() => setReviewing(null)} className="zp-btn-secondary !px-4 text-sm">Cancel</button>
                </div>
              ) : (
                <div className="flex gap-2">
                  <button onClick={() => setReviewing(c.id)} className="zp-btn-primary !py-1.5 !px-3 text-xs">Approve</button>
                  <button onClick={() => reject(c.id)} className="zp-btn-secondary !py-1.5 !px-3 text-xs">Reject</button>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
