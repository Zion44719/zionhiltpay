import React from 'react'
import { Link } from 'react-router-dom'
import { useAuth } from '../context/AuthContext.jsx'

export default function NotFound() {
  const { isAuthenticated } = useAuth()
  return (
    <div className="max-w-lg mx-auto px-6 py-24 text-center">
      <p className="font-mono text-gold-400 text-sm mb-3">404</p>
      <h1 className="font-display text-3xl text-white mb-4">Page not found</h1>
      <Link to={isAuthenticated ? '/dashboard' : '/'} className="zp-btn-primary">{isAuthenticated ? 'Back to dashboard' : 'Back home'}</Link>
    </div>
  )
}
