import React, { createContext, useContext, useState, useEffect, useCallback } from 'react'
import { getStoredAuth, setStoredAuth } from '../services/api'
import { authApi } from '../services/endpoints'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [auth, setAuth] = useState(getStoredAuth())
  const [profile, setProfile] = useState(null)
  const [loadingProfile, setLoadingProfile] = useState(false)

  const refreshProfile = useCallback(async () => {
    const stored = getStoredAuth()
    if (!stored?.access_token) {
      setProfile(null)
      return
    }
    setLoadingProfile(true)
    try {
      const { data } = await authApi.me()
      setProfile(data)
    } catch {
      setProfile(null)
    } finally {
      setLoadingProfile(false)
    }
  }, [])

  useEffect(() => {
    if (auth?.access_token) refreshProfile()
  }, [auth?.access_token, refreshProfile])

  const login = (data) => {
    setStoredAuth(data)
    setAuth(data)
  }

  const logout = async () => {
    const stored = getStoredAuth()
    try {
      if (stored?.refresh_token) await authApi.logout(stored.refresh_token)
    } catch {
      // best-effort server-side revoke; proceed with local logout regardless
    }
    setStoredAuth(null)
    setAuth(null)
    setProfile(null)
  }

  const value = {
    isAuthenticated: !!auth?.access_token,
    auth,
    profile,
    loadingProfile,
    login,
    logout,
    refreshProfile,
  }

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
