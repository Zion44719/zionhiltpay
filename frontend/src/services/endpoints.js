import { api } from './api'

export const authApi = {
  register: (payload) => api.post('/api/auth/register', payload),
  verifyOtp: (payload) => api.post('/api/auth/otp/verify', payload),
  resendOtp: (payload) => api.post('/api/auth/otp/resend', payload),
  login: (payload) => api.post('/api/auth/login', payload),
  logout: (refresh_token) => api.post('/api/auth/logout', { refresh_token }),
  setPin: (payload) => api.post('/api/auth/pin/set', payload),
  verifyPin: (payload) => api.post('/api/auth/pin/verify', payload),
  me: () => api.get('/api/auth/me'),
  usernameAvailable: (username) => api.get('/api/auth/username-available', { params: { username } }),
}

export const walletApi = {
  balance: () => api.get('/api/wallet/balance'),
  resolveRecipient: (identifier) => api.get('/api/wallet/resolve-recipient', { params: { identifier } }),
  deposit: (payload) => api.post('/api/wallet/deposit', payload),
  transfer: (payload) => api.post('/api/wallet/transfer', payload),
  withdraw: (payload) => api.post('/api/wallet/withdraw', payload),
  transactions: (page = 1, page_size = 20) =>
    api.get('/api/wallet/transactions', { params: { page, page_size } }),
  transaction: (id) => api.get(`/api/wallet/transactions/${id}`),
}

export const deviceApi = {
  list: () => api.get('/api/devices'),
  register: (payload) => api.post('/api/devices', payload),
  fileClaim: (payload) => api.post('/api/devices/claims', payload),
  myClaims: () => api.get('/api/devices/claims/mine'),
}

export const adminApi = {
  users: (params) => api.get('/api/admin/users', { params }),
  reviewKyc: (id, decision, note) => api.post(`/api/admin/users/${id}/kyc`, { decision, note }),
  revealId: (id) => api.post(`/api/admin/users/${id}/kyc/reveal`),
  transactions: (params) => api.get('/api/admin/transactions', { params }),
  user: (id) => api.get(`/api/admin/users/${id}`),
  freeze: (id, reason) => api.post(`/api/admin/users/${id}/freeze`, { reason }),
  unfreeze: (id) => api.post(`/api/admin/users/${id}/unfreeze`),
  fraudFlags: (resolved) => api.get('/api/admin/fraud-flags', { params: { resolved } }),
  resolveFraudFlag: (id, resolution_note) =>
    api.post(`/api/admin/fraud-flags/${id}/resolve`, { resolution_note }),
  claims: (status) => api.get('/api/admin/claims', { params: { status } }),
  reviewClaim: (id, payload) => api.post(`/api/admin/claims/${id}/review`, payload),
  stats: () => api.get('/api/admin/stats'),
  auditLogs: (page = 1, page_size = 50) =>
    api.get('/api/admin/audit-logs', { params: { page, page_size } }),
  getConfig: () => api.get('/api/admin/config'),
  updateConfig: (payload) => api.patch('/api/admin/config', payload),
}

export const agentApi = {
  status: () => api.get('/api/agent/status'),
  chat: (message, history) => api.post('/api/agent/chat', { message, history }),
  insights: (days) => api.post('/api/agent/insights', { days }),
  adminChat: (message, history) => api.post('/api/agent/admin/chat', { message, history }),
  triageFlag: (id) => api.post(`/api/agent/admin/fraud-flags/${id}/triage`),
  triageClaim: (id) => api.post(`/api/agent/admin/claims/${id}/triage`),
}
