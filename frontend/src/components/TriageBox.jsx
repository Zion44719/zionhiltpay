import React, { useState } from 'react'
import { apiErrorMessage } from '../services/api'

/** "AI triage" button + advisory result. `run` returns an axios promise of { data: { reply } }. */
export default function TriageBox({ run }) {
  const [state, setState] = useState({ loading: false, text: '', error: '' })

  const go = async () => {
    setState({ loading: true, text: '', error: '' })
    try {
      const { data } = await run()
      setState({ loading: false, text: data.reply, error: '' })
    } catch (err) {
      const msg = err?.response?.status === 503 ? "The AI copilot isn't enabled on this server." : apiErrorMessage(err)
      setState({ loading: false, text: '', error: msg })
    }
  }

  return (
    <div className="mt-3">
      <button onClick={go} disabled={state.loading} className="zp-btn-secondary !py-1.5 !px-3 text-xs">
        {state.loading ? 'Analyzing…' : state.text ? 'Re-run AI triage' : 'AI triage'}
      </button>
      {state.error && <p className="text-xs text-red-300 mt-2">{state.error}</p>}
      {state.text && (
        <div className="mt-3 rounded-lg border border-gold-500/30 bg-gold-500/5 p-4">
          <p className="text-[11px] uppercase tracking-wider text-gold-400 mb-2">AI recommendation — advisory only, verify before acting</p>
          <p className="text-sm text-slate-200 leading-relaxed whitespace-pre-wrap">{state.text}</p>
        </div>
      )}
    </div>
  )
}
