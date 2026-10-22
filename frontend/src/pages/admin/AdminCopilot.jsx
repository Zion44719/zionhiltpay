import React from 'react'
import ChatPanel from '../../components/ChatPanel.jsx'
import AgentGate from '../../components/AgentGate.jsx'
import { agentApi } from '../../services/endpoints'

export default function AdminCopilot() {
  return (
    <div className="max-w-2xl">
      <p className="text-slate-400 text-sm mb-5">
        Ask about platform health, open fraud flags, or a specific flag/claim ID. The copilot only recommends —
        every action (freeze, approve, reject, resolve) is still yours to take in the other tabs.
      </p>
      <AgentGate>
        <ChatPanel
          send={agentApi.adminChat}
          placeholder="e.g. Summarize the platform's current risk picture"
          suggestions={[
            'Give me platform stats',
            'Which open fraud flags should I look at first?',
          ]}
        />
      </AgentGate>
    </div>
  )
}
