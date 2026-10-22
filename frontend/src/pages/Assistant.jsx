import React from 'react'
import ChatPanel from '../components/ChatPanel.jsx'
import AgentGate from '../components/AgentGate.jsx'
import { agentApi } from '../services/endpoints'

export default function Assistant() {
  return (
    <div className="max-w-2xl mx-auto px-4 sm:px-6 py-10">
      <h1 className="font-display text-2xl sm:text-3xl text-white mb-1">Assistant</h1>
      <p className="text-slate-400 text-sm mb-6">
        Ask about your balances, charges, rewards, devices, and claims. The assistant can only read your
        account — it can't move money or change anything. Transfers always need your PIN.
      </p>
      <AgentGate>
        <ChatPanel
          send={agentApi.chat}
          placeholder="e.g. Why was I charged ₦150 on my last transfer?"
          suggestions={[
            'What is my balance?',
            'Explain my last transaction',
            'How much would a ₦20,000 transfer cost me?',
            'What is the status of my insurance claims?',
          ]}
        />
      </AgentGate>
    </div>
  )
}
