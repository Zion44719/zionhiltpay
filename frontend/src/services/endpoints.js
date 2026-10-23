import { api, API_BASE_URL } from './api'

// The shared client sends JSON by default, which would break file uploads: this lets axios/the browser add the multipart boundary.
const MULTIPART = { headers: { 'Content-Type': 'multipart/form-data' } }

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

export const profileApi = {
  get: () => api.get('/api/profile'),
  uploadPhoto: (file) => { const f = new FormData(); f.append('file', file); return api.post('/api/profile/photo', f, MULTIPART) },
  deletePhoto: () => api.delete('/api/profile/photo'),
  photo: () => api.get('/api/profile/photo', { responseType: 'blob' }),
}

export const tierApi = {
  overview: () => api.get('/api/tier'),
  upgrade: (formData) => api.post('/api/tier/upgrade', formData, MULTIPART),
}

export const bankApi = {
  list: () => api.get('/api/banks'),
  suggest: (account_number) => api.get('/api/banks/suggest', { params: { account_number } }),
  resolve: (bank_code, account_number) => api.get('/api/banks/resolve', { params: { bank_code, account_number } }),
  transfer: (payload) => api.post('/api/banks/transfer', payload),
}

export const loanApi = {
  offer: () => api.get('/api/loans/offer'),
  quote: (amount, tenor_days) => api.post('/api/loans/quote', { amount, tenor_days }),
  apply: (payload) => api.post('/api/loans/apply', payload),
  list: () => api.get('/api/loans'),
  repay: (id, amount, pin) => api.post(`/api/loans/${id}/repay`, { amount, pin }),
}

export const partnersApi = {
  list: () => api.get('/api/partners'),                       // public: the landing page needs no login
  logoUrl: (p) => `${API_BASE_URL}/api/partners/${p.id}/logo?v=${p.version}`,
}

export const adminApi = {
  partners: () => api.get('/api/admin/partners'),
  partnerLogo: (id) => api.get(`/api/admin/partners/${id}/logo`, { responseType: 'blob' }),
  createPartner: (formData) => api.post('/api/admin/partners', formData, MULTIPART),
  updatePartner: (id, formData) => api.patch(`/api/admin/partners/${id}`, formData, MULTIPART),
  deletePartner: (id) => api.delete(`/api/admin/partners/${id}`),
  tierRequests: (status) => api.get('/api/admin/tier-requests', { params: { status } }),
  decideTier: (id, decision, note) => api.post(`/api/admin/tier-requests/${id}/decision`, { decision, note }),
  tierDocument: (id) => api.get(`/api/admin/tier-requests/${id}/document`, { responseType: 'blob' }),
  revealBvn: (id) => api.post(`/api/admin/tier-requests/${id}/reveal-bvn`),
  loans: (params) => api.get('/api/admin/loans', { params }),
  userPhoto: (id) => api.get(`/api/admin/users/${id}/photo`, { responseType: 'blob' }),
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
