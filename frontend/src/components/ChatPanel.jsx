import React, { useEffect, useRef, useState } from 'react'
import { apiErrorMessage } from '../services/api'

const TOOL_LABELS = {
  get_balances: 'balances',
  list_recent_transactions: 'recent transactions',
  get_transaction: 'a transaction',
  explain_fee: 'fee calculator',
  list_devices: 'devices',
  list_claims: 'claims',
  spending_summary: 'spending summary',
  get_platform_stats: 'platform stats',
  list_open_fraud_flags: 'open fraud flags',
  get_fraud_flag_context: 'fraud flag details',
  get_claim_context: 'claim details',
}

/**
 * Shared chat UI. `send(message, history)` must return an axios promise resolving
 * to { data: { reply, tools_used } }. History is kept client-side and re-sent each turn;
 * the server sanitizes it, so it can't be used to smuggle in privileged instructions.
 */
export default function ChatPanel({ send, suggestions = [], placeholder = 'Ask a question…' }) {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const endRef = useRef(null)

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [messages, loading])

  const submit = async (text) => {
    const message = (text ?? input).trim()
    if (!message || loading) return
    setError('')
    setInput('')
    const history = messages.map(({ role, content }) => ({ role, content }))
    setMessages((m) => [...m, { role: 'user', content: message }])
    setLoading(true)
    try {
      const { data } = await send(message, history)
      setMessages((m) => [...m, { role: 'assistant', content: data.reply, tools: data.tools_used }])
    } catch (err) {
      setError(err?.response?.status === 429
        ? "You're sending messages too quickly. Please wait a moment."
        : apiErrorMessage(err))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="zp-card flex flex-col h-[28rem] sm:h-[32rem]">
      <div className="flex-1 overflow-y-auto p-4 sm:p-5 space-y-4">
        {messages.length === 0 && (
          <div className="text-center py-8">
            <p className="text-slate-500 text-sm mb-4">Try one of these:</p>
            <div className="flex flex-wrap gap-2 justify-center">
              {suggestions.map((s) => (
                <button key={s} onClick={() => submit(s)} className="zp-pill text-slate-300 border-ink-500 hover:border-gold-500 hover:text-gold-400 transition-colors">
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}
        {messages.map((m, i) => (
          <div key={i} className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            <div className={`max-w-[85%] rounded-2xl px-4 py-3 text-sm leading-relaxed whitespace-pre-wrap ${
              m.role === 'user' ? 'bg-gold-500 text-ink-950' : 'bg-ink-700 text-slate-100'
            }`}>
              {m.content}
              {m.role === 'assistant' && m.tools?.length > 0 && (
                <p className="mt-2 pt-2 border-t border-ink-500 text-[11px] font-mono text-slate-400">
                  checked: {[...new Set(m.tools)].map((t) => TOOL_LABELS[t] || t).join(', ')}
                </p>
              )}
            </div>
          </div>
        ))}
        {loading && (
          <div className="flex justify-start">
            <div className="bg-ink-700 text-slate-400 rounded-2xl px-4 py-3 text-sm flex items-center gap-2">
              <span className="w-3 h-3 rounded-full border-2 border-gold-500 border-t-transparent animate-spin" /> Thinking…
            </div>
          </div>
        )}
        <div ref={endRef} />
      </div>

      {error && <p className="px-5 pb-2 text-sm text-red-300">{error}</p>}
      <form onSubmit={(e) => { e.preventDefault(); submit() }} className="border-t border-ink-600 p-3 flex gap-2">
        <input className="zp-input" value={input} onChange={(e) => setInput(e.target.value)}
               maxLength={2000} placeholder={placeholder} disabled={loading} />
        <button type="submit" disabled={loading || !input.trim()} className="zp-btn-primary shrink-0">Send</button>
      </form>
    </div>
  )
}
