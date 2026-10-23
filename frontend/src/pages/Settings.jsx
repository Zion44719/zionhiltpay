import React from 'react'
import { Link } from 'react-router-dom'
import { useAuth } from '../context/AuthContext.jsx'
import { Avatar, Icon, KycBadge } from '../components/UI.jsx'
import { formatAccountNumber } from '../utils/format'

function Row({ to, icon, label, hint }) {
  return (
    <Link to={to} className="flex items-center gap-4 px-4 min-h-[56px] hover:bg-ink-700/60 transition-colors">
      <span className="text-gold-400 shrink-0"><Icon name={icon} /></span>
      <span className="flex-1 text-slate-100">{label}</span>
      {hint && <span className="text-xs text-slate-400">{hint}</span>}
      <span className="text-slate-500"><Icon name="chevron" size={16} /></span>
    </Link>
  )
}

function Group({ children }) {
  return <div className="zp-card divide-y divide-ink-700/60 overflow-hidden mb-4">{children}</div>
}

export default function Settings() {
  const { profile } = useAuth()
  return (
    <div className="max-w-2xl mx-auto px-4 sm:px-6 py-6 sm:py-10">
      <h1 className="font-display text-2xl sm:text-3xl text-white mb-5">Settings</h1>

      <Link to="/profile" className="zp-card p-4 mb-5 flex items-center gap-4 hover:border-gold-500/40 transition-colors">
        <Avatar name={profile?.full_name} has={profile?.has_photo} size={56} />
        <div className="min-w-0 flex-1">
          <p className="text-white font-medium truncate">{profile?.full_name || '…'}</p>
          <p className="text-xs text-slate-400 truncate">{profile?.username ? `@${profile.username} · ` : ''}{formatAccountNumber(profile?.account_number)}</p>
          <div className="mt-1.5 flex gap-2 flex-wrap">
            <span className="zp-pill text-gold-400 border-gold-500/40 bg-gold-500/10">Tier {profile?.account_tier ?? 1}</span>
            {profile?.kyc_status && profile.kyc_status !== 'not_submitted' && <KycBadge status={profile.kyc_status} />}
          </div>
        </div>
        <span className="text-slate-500"><Icon name="chevron" size={16} /></span>
      </Link>

      <Group>
        <Row to="/profile" icon="user" label="My profile" hint={profile?.has_photo ? undefined : 'Add a photo'} />
        <Row to="/settings/level" icon="level" label="Account level & limits" hint={`Tier ${profile?.account_tier ?? 1}`} />
        <Row to="/loans" icon="loan" label="Loans" />
      </Group>

      <Group>
        <Row to="/send-to-bank" icon="bank" label="Send to a bank account" />
        <Row to="/transactions" icon="history" label="Transaction history" />
        <Row to="/devices" icon="device" label="Devices & insurance" />
      </Group>

      <Group>
        <Row to="/insights" icon="spark" label="Spending insights" />
        <Row to="/assistant" icon="chat" label="Assistant" />
      </Group>
    </div>
  )
}
