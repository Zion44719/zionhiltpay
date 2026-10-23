import React, { useEffect, useState } from 'react'
import { partnersApi } from '../services/endpoints'

function Tile({ p, decorative }) {
  const [broken, setBroken] = useState(false)
  const inner = p.has_logo && !broken
    ? <img src={partnersApi.logoUrl(p)} alt={decorative ? '' : p.name} loading="lazy" draggable="false" onError={() => setBroken(true)} className="max-h-10 max-w-[120px] object-contain" />
    : <span className="font-display text-slate-800 text-base whitespace-nowrap">{p.name}</span>
  const tile = <div className="zp-partner-tile">{inner}</div>
  return p.website
    ? <a href={p.website} target="_blank" rel="noopener noreferrer" tabIndex={decorative ? -1 : undefined} aria-label={decorative ? undefined : `${p.name} (opens in a new tab)`}>{tile}</a>
    : tile
}

/** Scrolling strip of partner logos. Renders nothing until an admin has added at least one active partner. */
export default function PartnersMarquee() {
  const [partners, setPartners] = useState([])
  useEffect(() => { partnersApi.list().then(({ data }) => setPartners(data)).catch(() => {}) }, [])
  if (!partners.length) return null

  // Repeat the list until one "half" is wide enough to cover a big screen, then show the half twice: the loop is seamless.
  const reps = Math.max(1, Math.ceil(12 / partners.length))
  const half = Array.from({ length: reps }).flatMap((_, r) => partners.map((p) => ({ p, repeat: r > 0 })))
  const seconds = Math.max(24, half.length * 3.5)

  return (
    <section aria-label="Our partners" className="mt-14 sm:mt-20">
      <p className="text-center text-xs uppercase tracking-[0.2em] text-slate-500 mb-5">Our partners</p>
      <div className="zp-marquee" style={{ '--zp-marquee-duration': `${seconds}s` }}>
        <ul className="zp-marquee-track">
          {half.map(({ p, repeat }, i) => (
            <li key={`a${i}`} className={repeat ? 'zp-marquee-dup' : undefined} aria-hidden={repeat ? 'true' : undefined}><Tile p={p} decorative={repeat} /></li>
          ))}
          {half.map(({ p }, i) => (
            <li key={`b${i}`} className="zp-marquee-dup" aria-hidden="true"><Tile p={p} decorative /></li>
          ))}
        </ul>
      </div>
    </section>
  )
}
