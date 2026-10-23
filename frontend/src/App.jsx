import React from 'react'
import { Routes, Route } from 'react-router-dom'
import Navbar from './components/Navbar.jsx'
import { ProtectedRoute, AdminRoute } from './components/RouteGuards.jsx'

import Landing from './pages/Landing.jsx'
import Register from './pages/Register.jsx'
import VerifyOtp from './pages/VerifyOtp.jsx'
import Login from './pages/Login.jsx'
import SetPin from './pages/SetPin.jsx'
import Dashboard from './pages/Dashboard.jsx'
import Transfer from './pages/Transfer.jsx'
import Deposit from './pages/Deposit.jsx'
import Withdraw from './pages/Withdraw.jsx'
import Transactions from './pages/Transactions.jsx'
import Devices from './pages/Devices.jsx'
import Settings from './pages/Settings.jsx'
import Profile from './pages/Profile.jsx'
import AccountLevel from './pages/AccountLevel.jsx'
import Loans from './pages/Loans.jsx'
import SendToBank from './pages/SendToBank.jsx'
import Assistant from './pages/Assistant.jsx'
import Insights from './pages/Insights.jsx'
import NotFound from './pages/NotFound.jsx'

import { AdminLayout } from './pages/admin/AdminOverview.jsx'
import AdminOverview from './pages/admin/AdminOverview.jsx'
import AdminUsers from './pages/admin/AdminUsers.jsx'
import AdminTransactions from './pages/admin/AdminTransactions.jsx'
import AdminAudit from './pages/admin/AdminAudit.jsx'
import AdminTier from './pages/admin/AdminTier.jsx'
import AdminLoans from './pages/admin/AdminLoans.jsx'
import AdminPartners from './pages/admin/AdminPartners.jsx'
import AdminFraud from './pages/admin/AdminFraud.jsx'
import AdminClaims from './pages/admin/AdminClaims.jsx'
import AdminConfig from './pages/admin/AdminConfig.jsx'
import AdminCopilot from './pages/admin/AdminCopilot.jsx'

export default function App() {
  return (
    <div className="min-h-screen flex flex-col">
      <Navbar />
      <main className="flex-1">
        <Routes>
          <Route path="/" element={<Landing />} />
          <Route path="/register" element={<Register />} />
          <Route path="/verify-otp" element={<VerifyOtp />} />
          <Route path="/login" element={<Login />} />
          <Route path="/set-pin" element={<ProtectedRoute><SetPin /></ProtectedRoute>} />

          <Route path="/dashboard" element={<ProtectedRoute><Dashboard /></ProtectedRoute>} />
          <Route path="/transfer" element={<ProtectedRoute><Transfer /></ProtectedRoute>} />
          <Route path="/deposit" element={<ProtectedRoute><Deposit /></ProtectedRoute>} />
          <Route path="/withdraw" element={<ProtectedRoute><Withdraw /></ProtectedRoute>} />
          <Route path="/transactions" element={<ProtectedRoute><Transactions /></ProtectedRoute>} />
          <Route path="/devices" element={<ProtectedRoute><Devices /></ProtectedRoute>} />
          <Route path="/settings" element={<ProtectedRoute><Settings /></ProtectedRoute>} />
          <Route path="/settings/level" element={<ProtectedRoute><AccountLevel /></ProtectedRoute>} />
          <Route path="/profile" element={<ProtectedRoute><Profile /></ProtectedRoute>} />
          <Route path="/loans" element={<ProtectedRoute><Loans /></ProtectedRoute>} />
          <Route path="/send-to-bank" element={<ProtectedRoute><SendToBank /></ProtectedRoute>} />
          <Route path="/assistant" element={<ProtectedRoute><Assistant /></ProtectedRoute>} />
          <Route path="/insights" element={<ProtectedRoute><Insights /></ProtectedRoute>} />

          <Route path="/admin" element={<AdminRoute><AdminLayout /></AdminRoute>}>
            <Route index element={<AdminOverview />} />
            <Route path="users" element={<AdminUsers />} />
            <Route path="transactions" element={<AdminTransactions />} />
            <Route path="audit" element={<AdminAudit />} />
            <Route path="tier" element={<AdminTier />} />
            <Route path="loans" element={<AdminLoans />} />
            <Route path="partners" element={<AdminPartners />} />
            <Route path="fraud" element={<AdminFraud />} />
            <Route path="claims" element={<AdminClaims />} />
            <Route path="copilot" element={<AdminCopilot />} />
            <Route path="config" element={<AdminConfig />} />
          </Route>

          <Route path="*" element={<NotFound />} />
        </Routes>
      </main>
      <footer className="border-t border-ink-700 py-6 text-center text-xs text-slate-600">
        ZionhiltPay — Powered by Zionhilt · Built on a real double-entry ledger
      </footer>
    </div>
  )
}
