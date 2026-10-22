import React from 'react'
import { Link } from 'react-router-dom'

export default function Landing() {
  return (
    <div className="max-w-6xl mx-auto px-4 sm:px-6 py-16 sm:py-24">
      <div className="max-w-2xl">
        <span className="zp-pill text-gold-400 border-gold-500/40 bg-gold-500/10 mb-6 inline-block">
          Powered by Zionhilt
        </span>
        <h1 className="font-display text-4xl sm:text-5xl text-white leading-tight mb-6">
          Every transaction pays you back — and quietly insures your devices.
        </h1>
        <p className="text-slate-400 text-lg leading-relaxed mb-8">
          ZionhiltPay is a digital wallet built on a real double-entry ledger. Send money,
          get cashback rewards, and automatically build up device insurance coverage for
          your phone or laptop — all from the transactions you're already making.
        </p>
        <div className="flex gap-3">
          <Link to="/register" className="zp-btn-primary">Create your wallet</Link>
          <Link to="/login" className="zp-btn-secondary">I already have an account</Link>
        </div>
      </div>

      <div className="grid sm:grid-cols-3 gap-5 mt-20">
        <div className="zp-card p-6">
          <p className="text-gold-400 font-display text-xl mb-2">Rewards</p>
          <p className="text-sm text-slate-400 leading-relaxed">
            A share of the fee on every transfer comes back to you as cashback,
            automatically, every time.
          </p>
        </div>
        <div className="zp-card p-6">
          <p className="text-teal-300 font-display text-xl mb-2">Device Insurance</p>
          <p className="text-sm text-slate-400 leading-relaxed">
            Part of every commission builds a personal insurance pool you can claim
            against if your phone or laptop is lost, stolen, or damaged.
          </p>
        </div>
        <div className="zp-card p-6">
          <p className="text-slate-200 font-display text-xl mb-2">Real Ledger</p>
          <p className="text-sm text-slate-400 leading-relaxed">
            Every balance is backed by a double-entry ledger — auditable, balanced,
            and immutable by design.
          </p>
        </div>
      </div>
    </div>
  )
}
