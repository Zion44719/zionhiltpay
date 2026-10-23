import React, { useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { useAuth } from '../context/AuthContext.jsx'
import { profileApi } from '../services/endpoints'
import { apiErrorMessage } from '../services/api'
import { Avatar, Alert, CopyButton, KycBadge } from '../components/UI.jsx'
import { formatAccountNumber, formatDate } from '../utils/format'

const MAX_BYTES = 3_000_000

function Field({ label, children }) {
  return (
    <div className="flex items-start justify-between gap-4 py-3 border-b border-ink-700/60 last:border-0">
      <dt className="text-xs uppercase tracking-wider text-slate-500 pt-0.5 shrink-0">{label}</dt>
      <dd className="text-sm text-slate-100 text-right break-all min-w-0">{children}</dd>
    </div>
  )
}

export default function Profile() {
  const { profile, refreshProfile } = useAuth()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [ok, setOk] = useState('')
  const [version, setVersion] = useState(0)
  const input = useRef(null)

  const onPick = async (e) => {
    const file = e.target.files?.[0]
    e.target.value = ''
    setError(''); setOk('')
    if (!file) return
    if (!file.type.startsWith('image/')) return setError('Please choose a photo (JPEG, PNG or WebP).')
    if (file.size > MAX_BYTES) return setError('That photo is too large. Please choose one under 3 MB.')
    setBusy(true)
    try {
      await profileApi.uploadPhoto(file)
      await refreshProfile()
      setVersion((v) => v + 1)
      setOk('Profile photo updated.')
    } catch (err) { setError(apiErrorMessage(err)) } finally { setBusy(false) }
  }

  const remove = async () => {
    setBusy(true); setError(''); setOk('')
    try { await profileApi.deletePhoto(); await refreshProfile(); setOk('Photo removed.') } catch (err) { setError(apiErrorMessage(err)) } finally { setBusy(false) }
  }

  return (
    <div className="max-w-lg mx-auto px-4 sm:px-6 py-6 sm:py-10">
      <Link to="/settings" className="text-sm text-slate-400 hover:text-white">← Settings</Link>
      <h1 className="font-display text-2xl sm:text-3xl text-white mt-2 mb-6">My profile</h1>
      <Alert type="error">{error}</Alert>
      <Alert type="success">{ok}</Alert>

      <div className="zp-card p-5 mb-5 flex flex-col items-center text-center">
        <Avatar name={profile?.full_name} has={profile?.has_photo} version={version} size={112} />
        <p className="text-white font-medium mt-3">{profile?.full_name}</p>
        <p className="text-xs text-slate-400 mb-4">{profile?.username ? `@${profile.username}` : ''}</p>
        <input ref={input} type="file" accept="image/jpeg,image/png,image/webp" className="sr-only" onChange={onPick} aria-label="Choose a profile photo" />
        <div className="flex flex-wrap gap-3 justify-center w-full">
          <button type="button" disabled={busy} onClick={() => input.current?.click()} className="zp-btn-primary min-h-[48px]">
            {busy ? 'Uploading…' : profile?.has_photo ? 'Change photo' : 'Add photo'}
          </button>
          {profile?.has_photo && <button type="button" disabled={busy} onClick={remove} className="zp-btn-secondary min-h-[48px]">Remove</button>}
        </div>
        <p className="text-xs text-slate-500 mt-3">JPEG, PNG or WebP, up to 3 MB. We crop it to a square and strip location data.</p>
      </div>

      <dl className="zp-card px-5">
        <Field label="Account number"><span className="zp-amount tracking-wider">{formatAccountNumber(profile?.account_number)}</span> <CopyButton text={profile?.account_number || ''} className="ml-2 !py-1 !px-3" /></Field>
        <Field label="Account level"><Link to="/settings/level" className="text-gold-400 hover:underline">Tier {profile?.account_tier ?? 1}</Link></Field>
        <Field label="Identity">{profile?.kyc_status ? <KycBadge status={profile.kyc_status} /> : '—'}</Field>
        <Field label="Email">{profile?.email}</Field>
        <Field label="Phone">{profile?.phone_number}</Field>
        <Field label="Member since">{profile?.created_at ? formatDate(profile.created_at) : '—'}</Field>
      </dl>
    </div>
  )
}
