import React, { useEffect, useState } from 'react'
import { Link, NavLink, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext.jsx'
import { Avatar } from './UI.jsx'

const desktopLink = ({ isActive }) =>
  `px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
    isActive ? 'bg-ink-700 text-gold-400' : 'text-slate-300 hover:text-white hover:bg-ink-800'
  }`

const mobileLink = ({ isActive }) =>
  `flex items-center min-h-[48px] px-4 rounded-xl text-base font-medium transition-colors ${
    isActive ? 'bg-ink-700 text-gold-400' : 'text-slate-200 hover:bg-ink-800'
  }`

// [path, label, exact match, shown in the desktop bar]. Everything is in the phone menu.
const LINKS = [
  ['/dashboard', 'Dashboard', true, true],
  ['/transfer', 'Send money', false, true],
  ['/send-to-bank', 'Send to bank', false, true],
  ['/deposit', 'Fund wallet', false, true],
  ['/loans', 'Loans', false, true],
  ['/transactions', 'History', false, true],
  ['/settings', 'Settings', false, true],
  ['/devices', 'Devices & insurance', false, false],
  ['/insights', 'Insights', false, false],
  ['/assistant', 'Assistant', false, false],
]

export default function Navbar() {
  const { isAuthenticated, profile, logout } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [open, setOpen] = useState(false)

  const isAdmin = profile?.role === 'admin' || profile?.role === 'super_admin'

  // close the menu on navigation and on Escape
  useEffect(() => { setOpen(false) }, [location.pathname])
  useEffect(() => {
    const onKey = (e) => e.key === 'Escape' && setOpen(false)
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  const handleLogout = async () => {
    setOpen(false)
    await logout()
    navigate('/login')
  }

  return (
    <header className="border-b border-ink-700 bg-ink-950/90 backdrop-blur sticky top-0 z-40">
      <div className="max-w-6xl mx-auto px-3 min-[360px]:px-4 sm:px-6 h-16 flex items-center justify-between gap-2 sm:gap-3">
        <Link to={isAuthenticated ? '/dashboard' : '/'} className="flex items-center gap-2 shrink-0" aria-label={isAuthenticated ? 'ZionhiltPay, go to your dashboard' : 'ZionhiltPay home'}>
          <span className="w-8 h-8 rounded-lg bg-gold-500 text-ink-950 font-display font-bold flex items-center justify-center">Z</span>
          <span className="font-display text-base sm:text-lg text-white tracking-tight">ZionhiltPay</span>
        </Link>

        {isAuthenticated && (
          <nav className="hidden xl:flex items-center gap-1" aria-label="Main">
            {LINKS.filter((l) => l[3]).map(([to, label, end]) => (
              <NavLink key={to} to={to} end={end} className={desktopLink}>{label}</NavLink>
            ))}
            {isAdmin && <NavLink to="/admin" className={desktopLink}>Admin</NavLink>}
          </nav>
        )}

        <div className="flex items-center gap-2 sm:gap-3">
          {isAuthenticated ? (
            <>
              <Link to="/settings" className="flex items-center gap-2 min-w-0" aria-label="Settings and profile">
                <Avatar name={profile?.full_name} has={profile?.has_photo} size={36} />
                <span className="hidden sm:block text-sm text-slate-400 truncate max-w-[9rem]">
                  {profile?.username ? `@${profile.username}` : profile?.full_name?.split(' ')[0] || '…'}
                </span>
              </Link>
              <button onClick={handleLogout} className="hidden xl:inline-flex zp-btn-secondary !px-4 !py-2 text-sm">Log out</button>
              <button
                type="button"
                className="xl:hidden inline-flex items-center justify-center w-11 h-11 rounded-xl border border-ink-600 bg-ink-800 text-slate-100"
                aria-label={open ? 'Close menu' : 'Open menu'}
                aria-expanded={open}
                aria-controls="mobile-menu"
                onClick={() => setOpen((o) => !o)}
              >
                <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
                  {open ? <path d="M6 6l12 12M18 6L6 18" /> : <path d="M4 7h16M4 12h16M4 17h16" />}
                </svg>
              </button>
            </>
          ) : (
            <>
              <Link to="/login" className="zp-btn-ghost text-sm !px-2 sm:!px-4">Log in</Link>
              <Link to="/register" className="zp-btn-primary !px-3 sm:!px-4 !py-2 text-sm whitespace-nowrap">Get started</Link>
            </>
          )}
        </div>
      </div>

      {isAuthenticated && open && (
        <>
          <button className="xl:hidden fixed inset-0 top-16 bg-black/60 z-30" aria-label="Close menu" onClick={() => setOpen(false)} />
          <nav
            id="mobile-menu"
            aria-label="Mobile"
            className="xl:hidden absolute inset-x-0 top-16 z-40 bg-ink-900 border-b border-ink-600 px-3 pt-3 pb-4 max-h-[calc(100vh-4rem)] overflow-y-auto shadow-2xl"
          >
            <div className="px-4 pb-3 mb-2 border-b border-ink-700">
              <p className="text-white font-medium truncate">{profile?.full_name || '…'}</p>
              <p className="text-xs text-slate-400 truncate">
                {profile?.username ? `@${profile.username}` : profile?.email}
                {profile?.account_number ? ` · ${profile.account_number}` : ''}
              </p>
            </div>
            {LINKS.map(([to, label, end]) => (
              <NavLink key={to} to={to} end={end} className={mobileLink}>{label}</NavLink>
            ))}
            {isAdmin && <NavLink to="/admin" className={mobileLink}>Admin dashboard</NavLink>}
            <button onClick={handleLogout} className="mt-3 w-full zp-btn-secondary min-h-[48px]">Log out</button>
          </nav>
        </>
      )}
    </header>
  )
}
