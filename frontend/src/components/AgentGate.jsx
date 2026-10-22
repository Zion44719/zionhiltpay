import React, { useEffect, useState } from 'react'
import { agentApi } from '../services/endpoints'

/** Renders children only when the server has the AI agent enabled; otherwise a clear notice. */
export default function AgentGate({ children }) {
  const [enabled, setEnabled] = useState(null)
  useEffect(() => {
    agentApi.status().then(({ data }) => setEnabled(data.enabled)).catch(() => setEnabled(false))
  }, [])
  if (enabled === null) return <p className="text-sm text-slate-500">Checking assistant availability…</p>
  if (!enabled) {
    return (
      <div className="zp-card p-6 text-sm text-slate-400">
        The AI assistant isn't enabled on this server yet. Set <span className="font-mono text-gold-400">ANTHROPIC_API_KEY</span> in
        the backend environment and restart to turn it on.
      </div>
    )
  }
  return children
}
