import React, { useCallback, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { adminApi } from '../../services/endpoints'
import { apiErrorMessage } from '../../services/api'
import { Loader, Alert } from '../../components/UI.jsx'

const MAX_BYTES = 1_000_000

function Thumb({ p, version }) {
  const [url, setUrl] = useState(null)
  useEffect(() => {
    if (!p.has_logo) { setUrl(null); return undefined }
    let alive = true, obj = null
    adminApi.partnerLogo(p.id).then(({ data }) => { if (alive) { obj = URL.createObjectURL(data); setUrl(obj) } }).catch(() => alive && setUrl(null))
    return () => { alive = false; if (obj) URL.revokeObjectURL(obj) }
  }, [p.id, p.has_logo, p.version, version])
  return (
    <div className="w-24 h-14 rounded-lg bg-white/95 flex items-center justify-center shrink-0 px-2 overflow-hidden">
      {url ? <img src={url} alt={`${p.name} logo`} className="max-h-10 max-w-full object-contain" /> : <span className="text-[11px] text-slate-500 text-center leading-tight">No logo</span>}
    </div>
  )
}

function Modal({ title, children, onClose }) {
  return (
    <div className="fixed inset-0 bg-black/70 backdrop-blur-sm z-50 flex items-end sm:items-center justify-center sm:px-4" onClick={onClose}>
      <div className="zp-card w-full sm:max-w-md p-5 sm:p-6 rounded-b-none sm:rounded-b-2xl max-h-[92vh] overflow-y-auto" role="dialog" aria-modal="true" aria-label={title} onClick={(e) => e.stopPropagation()}>
        <h3 className="font-display text-lg text-white mb-3">{title}</h3>{children}
      </div>
    </div>
  )
}

function PartnerForm({ initial, onSubmit, onCancel, busy, submitLabel }) {
  const [name, setName] = useState(initial?.name || '')
  const [website, setWebsite] = useState(initial?.website || '')
  const [order, setOrder] = useState(String(initial?.sort_order ?? 0))
  const [active, setActive] = useState(initial?.is_active ?? true)
  const [file, setFile] = useState(null)
  const [preview, setPreview] = useState(null)
  const [removeLogo, setRemoveLogo] = useState(false)
  const [error, setError] = useState('')
  const input = useRef(null)
  useEffect(() => () => { if (preview) URL.revokeObjectURL(preview) }, [preview])

  const pick = (e) => {
    const f = e.target.files?.[0]; e.target.value = ''
    setError('')
    if (!f) return
    if (!f.type.startsWith('image/') || f.type === 'image/svg+xml') return setError('Choose a PNG, JPEG or WebP image (SVG files are not accepted).')
    if (f.size > MAX_BYTES) return setError('That logo is over 1 MB. Please use a smaller file.')
    setFile(f); setRemoveLogo(false); setPreview(URL.createObjectURL(f))
  }
  const submit = (e) => {
    e.preventDefault(); setError('')
    if (name.trim().length < 2) return setError('Enter the partner name.')
    const f = new FormData()
    f.append('name', name.trim()); f.append('website', website.trim()); f.append('sort_order', order || '0'); f.append('is_active', String(active))
    if (file) f.append('logo', file)
    if (removeLogo) f.append('remove_logo', 'true')
    onSubmit(f)
  }

  return (
    <form onSubmit={submit} className="space-y-4">
      {error && <p className="text-xs text-red-300" role="alert">{error}</p>}
      <div><label className="zp-label" htmlFor="p-name">Company name</label><input id="p-name" className="zp-input" value={name} maxLength={80} onChange={(e) => setName(e.target.value)} placeholder="Company name" /></div>
      <div><label className="zp-label" htmlFor="p-web">Website (optional)</label><input id="p-web" className="zp-input" inputMode="url" autoCapitalize="none" value={website} onChange={(e) => setWebsite(e.target.value)} placeholder="https://example.com" /></div>
      <div>
        <span className="zp-label">Logo</span>
        <input ref={input} type="file" accept="image/png,image/jpeg,image/webp" className="sr-only" onChange={pick} aria-label="Choose a logo image" />
        <div className="rounded-lg bg-white/95 h-20 flex items-center justify-center mb-2 overflow-hidden">
          {preview ? <img src={preview} alt="Logo preview" className="max-h-14 max-w-[80%] object-contain" /> : <span className="text-xs text-slate-500">{initial?.has_logo && !removeLogo ? 'Current logo kept' : 'No logo: the name is shown instead'}</span>}
        </div>
        <div className="flex gap-2">
          <button type="button" className="zp-btn-secondary flex-1 min-h-[44px]" onClick={() => input.current?.click()}>{file ? 'Choose another' : 'Choose a logo'}</button>
          {initial?.has_logo && !file && <button type="button" className="zp-btn-secondary min-h-[44px]" onClick={() => setRemoveLogo((v) => !v)}>{removeLogo ? 'Keep it' : 'Remove'}</button>}
        </div>
        <p className="text-xs text-slate-500 mt-1.5">A transparent PNG works best. It is shown on a white tile and scaled to fit. Only upload logos you have permission to display.</p>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div><label className="zp-label" htmlFor="p-order">Order</label><input id="p-order" className="zp-input" type="number" inputMode="numeric" min="0" max="999" value={order} onChange={(e) => setOrder(e.target.value)} /></div>
        <label className="flex items-center gap-3 text-sm text-slate-300 cursor-pointer pt-7"><input type="checkbox" className="w-5 h-5 accent-[#DDAA4E]" checked={active} onChange={(e) => setActive(e.target.checked)} />Show on site</label>
      </div>
      <div className="flex gap-3">
        <button type="button" onClick={onCancel} className="zp-btn-secondary flex-1 min-h-[44px]">Cancel</button>
        <button type="submit" disabled={busy} className="zp-btn-primary flex-1 min-h-[44px]">{busy ? 'Saving…' : submitLabel}</button>
      </div>
    </form>
  )
}

export default function AdminPartners() {
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [ok, setOk] = useState('')
  const [dialog, setDialog] = useState(null)   // {type:'add'|'edit'|'delete', row?}
  const [busy, setBusy] = useState(false)
  const [version, setVersion] = useState(0)

  const load = useCallback(async () => {
    setLoading(true); setError('')
    try { const { data } = await adminApi.partners(); setRows(data) } catch (e) { setError(apiErrorMessage(e)) } finally { setLoading(false) }
  }, [])
  useEffect(() => { load() }, [load])

  const run = async (fn, msg) => {
    setBusy(true); setError('')
    try { await fn(); setOk(msg); setDialog(null); setVersion((v) => v + 1); await load() }
    catch (e) { setError(apiErrorMessage(e)); if (dialog?.type === 'delete') setDialog(null) } finally { setBusy(false) }
  }
  const toggle = (p) => { const f = new FormData(); f.append('is_active', String(!p.is_active)); run(() => adminApi.updatePartner(p.id, f), p.is_active ? 'Hidden from the site.' : 'Now showing on the site.') }

  return (
    <div>
      <p className="text-xs text-slate-500 mb-4">These logos scroll across the public landing page. Add only companies you genuinely work with, and only logos you have permission to display. <Link to="/" className="text-gold-400 hover:underline">View the landing page</Link></p>
      <Alert type="error">{error}</Alert>
      <Alert type="success">{ok}</Alert>
      <button onClick={() => { setOk(''); setDialog({ type: 'add' }) }} className="zp-btn-primary w-full sm:w-auto min-h-[48px] mb-4">+ Add a partner</button>

      {loading ? <Loader /> : (
        <div className="space-y-3">
          {rows.length === 0 && <p className="text-sm text-slate-500 zp-card p-8 text-center">No partners yet. Add one and its logo will start scrolling across the landing page.</p>}
          {rows.map((p) => (
            <article key={p.id} className={`zp-card p-4 flex items-center gap-3 ${p.is_active ? '' : 'opacity-60'}`}>
              <Thumb p={p} version={version} />
              <div className="min-w-0 flex-1">
                <h3 className="text-slate-100 font-medium break-words">{p.name}</h3>
                <p className="text-xs text-slate-500 break-all">{p.website || 'No website'}</p>
                <p className="text-xs text-slate-500">Order {p.sort_order} · {p.is_active ? 'Showing' : 'Hidden'}</p>
              </div>
              <div className="flex flex-col gap-2 shrink-0">
                <button onClick={() => toggle(p)} className="zp-btn-secondary !px-3 !py-2 text-xs min-h-[40px]">{p.is_active ? 'Hide' : 'Show'}</button>
                <button onClick={() => { setOk(''); setDialog({ type: 'edit', row: p }) }} className="zp-btn-secondary !px-3 !py-2 text-xs min-h-[40px]">Edit</button>
              </div>
            </article>
          ))}
        </div>
      )}

      {dialog?.type === 'add' && (
        <Modal title="Add a partner" onClose={() => setDialog(null)}>
          <PartnerForm busy={busy} submitLabel="Add partner" onCancel={() => setDialog(null)} onSubmit={(f) => run(() => adminApi.createPartner(f), 'Partner added.')} />
        </Modal>
      )}
      {dialog?.type === 'edit' && (
        <Modal title={`Edit ${dialog.row.name}`} onClose={() => setDialog(null)}>
          <PartnerForm initial={dialog.row} busy={busy} submitLabel="Save changes" onCancel={() => setDialog(null)} onSubmit={(f) => run(() => adminApi.updatePartner(dialog.row.id, f), 'Partner updated.')} />
          <button onClick={() => setDialog({ type: 'delete', row: dialog.row })} className="mt-4 w-full text-sm text-red-300 hover:underline min-h-[44px]">Delete this partner…</button>
        </Modal>
      )}
      {dialog?.type === 'delete' && (
        <Modal title={`Delete ${dialog.row.name}?`} onClose={() => setDialog(null)}>
          <p className="text-sm text-slate-300 mb-4">This removes the partner and its logo from the site. This can't be undone.</p>
          <div className="flex gap-3">
            <button onClick={() => setDialog(null)} className="zp-btn-secondary flex-1 min-h-[44px]">Cancel</button>
            <button disabled={busy} onClick={() => run(() => adminApi.deletePartner(dialog.row.id), 'Partner deleted.')} className="zp-btn-primary flex-1 min-h-[44px]">Delete</button>
          </div>
        </Modal>
      )}
    </div>
  )
}
