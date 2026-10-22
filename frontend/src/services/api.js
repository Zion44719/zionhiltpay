import axios from 'axios'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

export const api = axios.create({
  baseURL: API_BASE_URL,
  headers: { 'Content-Type': 'application/json' },
})

function getStoredAuth() {
  try {
    return JSON.parse(localStorage.getItem('zhp_auth') || 'null')
  } catch {
    return null
  }
}

function setStoredAuth(auth) {
  if (auth) localStorage.setItem('zhp_auth', JSON.stringify(auth))
  else localStorage.removeItem('zhp_auth')
}

api.interceptors.request.use((config) => {
  const auth = getStoredAuth()
  if (auth?.access_token) {
    config.headers.Authorization = `Bearer ${auth.access_token}`
  }
  return config
})

let isRefreshing = false
let refreshQueue = []

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const original = error.config
    if (error.response?.status === 401 && !original._retry) {
      const auth = getStoredAuth()
      if (!auth?.refresh_token) {
        setStoredAuth(null)
        window.location.href = '/login'
        return Promise.reject(error)
      }

      if (isRefreshing) {
        return new Promise((resolve, reject) => {
          refreshQueue.push({ resolve, reject, original })
        })
      }

      original._retry = true
      isRefreshing = true
      try {
        const { data } = await axios.post(`${API_BASE_URL}/api/auth/refresh`, {
          refresh_token: auth.refresh_token,
        })
        setStoredAuth(data)
        api.defaults.headers.common.Authorization = `Bearer ${data.access_token}`
        refreshQueue.forEach(({ resolve, original: o }) => {
          o.headers.Authorization = `Bearer ${data.access_token}`
          resolve(api(o))
        })
        refreshQueue = []
        original.headers.Authorization = `Bearer ${data.access_token}`
        return api(original)
      } catch (refreshError) {
        refreshQueue.forEach(({ reject }) => reject(refreshError))
        refreshQueue = []
        setStoredAuth(null)
        window.location.href = '/login'
        return Promise.reject(refreshError)
      } finally {
        isRefreshing = false
      }
    }
    return Promise.reject(error)
  }
)

export { getStoredAuth, setStoredAuth }

export function apiErrorMessage(err) {
  if (err?.code === 'ERR_NETWORK' || (err?.request && !err?.response)) {
    return "Can't reach the server. Check that the backend is running, and that you opened the site at http://localhost:5173 (not a 172.x / 192.168.x address)."
  }
  const detail = err?.response?.data?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail) && detail[0]?.msg) return String(detail[0].msg).replace(/^Value error,\s*/i, '')
  if (err?.response?.status === 429) return 'Too many attempts. Please wait a minute and try again.'
  return err?.message || 'Something went wrong. Please try again.'
}
