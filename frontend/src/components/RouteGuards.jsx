import React from 'react'
import { Navigate, useLocation } from 'react-router-dom'
import { useAuth } from '../context/AuthContext.jsx'

export function ProtectedRoute({ children }) {
  const { isAuthenticated } = useAuth()
  const location = useLocation()
  if (!isAuthenticated) {
    return <Navigate to="/login" state={{ from: location }} replace />
  }
  return children
}

export function AdminRoute({ children }) {
  const { isAuthenticated, profile, loadingProfile } = useAuth()
  const location = useLocation()
  if (!isAuthenticated) return <Navigate to="/login" state={{ from: location }} replace />
  if (loadingProfile) return <div className="max-w-6xl mx-auto px-6 py-16 text-slate-400">Loading…</div>
  if (profile && profile.role !== 'admin' && profile.role !== 'super_admin') {
    return <Navigate to="/dashboard" replace />
  }
  return children
}
