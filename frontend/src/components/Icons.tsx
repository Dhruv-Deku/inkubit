import type { Status } from '../types'

const base = { width: 16, height: 16, viewBox: '0 0 16 16', fill: 'none', 'aria-hidden': true } as const

export const Check = ({ color = 'var(--pass)' }: { color?: string }) => (
  <svg {...base}><path d="M3.5 8.5l3 3 6-7" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" /></svg>
)
export const Cross = ({ color = 'var(--fail)' }: { color?: string }) => (
  <svg {...base}><path d="M4.5 4.5l7 7m0-7l-7 7" stroke={color} strokeWidth="2" strokeLinecap="round" /></svg>
)
export const Warn = () => (
  <svg {...base}><path d="M8 2.5l6 10.5H2L8 2.5z" stroke="var(--warn)" strokeWidth="1.6" strokeLinejoin="round" /><path d="M8 6.5v3" stroke="var(--warn)" strokeWidth="1.6" strokeLinecap="round" /><circle cx="8" cy="11.4" r="0.9" fill="var(--warn)" /></svg>
)
export const Dot = () => (
  <svg {...base}><circle cx="8" cy="8" r="3" fill="var(--muted)" /></svg>
)
export const Upload = () => (
  <svg width="28" height="28" viewBox="0 0 24 24" fill="none" aria-hidden><path d="M12 15V4m0 0l-4 4m4-4l4 4M5 15v3a2 2 0 002 2h10a2 2 0 002-2v-3" stroke="var(--text-2)" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" /></svg>
)
export const Copy = () => (
  <svg {...base}><rect x="5" y="5" width="8" height="9" rx="2" stroke="currentColor" strokeWidth="1.4" /><path d="M3 10.5V4a2 2 0 012-2h5" stroke="currentColor" strokeWidth="1.4" /></svg>
)
export const Up = () => (<svg {...base}><path d="M4 10l4-4 4 4" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" /></svg>)
export const Down = () => (<svg {...base}><path d="M4 6l4 4 4-4" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" /></svg>)
export const Trash = () => (
  <svg {...base}><path d="M3.5 4.5h9M6.5 4.5V3h3v1.5M5 4.5l.5 8.5h5l.5-8.5" stroke="currentColor" strokeWidth="1.4" strokeLinejoin="round" /></svg>
)

export function StatusIcon({ status, live }: { status: Status; live?: boolean }) {
  if (status === 'running') return live ? <div className="spin" /> : <Dot />
  if (status === 'ok') return <Check />
  if (status === 'fail') return <Cross />
  if (status === 'warn') return <Warn />
  return <Dot />
}

export const Logo = () => (
  <svg width="30" height="30" viewBox="0 0 32 32" aria-hidden>
    <rect width="32" height="32" rx="8" fill="#1f2025" />
    <path d="M16 4.5C16 4.5 7.5 13.6 7.5 19a8.5 8.5 0 0 0 17 0C24.5 13.6 16 4.5 16 4.5Z" fill="#3987e5" />
    <circle cx="16" cy="19.2" r="4.6" fill="none" stroke="#f4f3f0" strokeWidth="1.5" />
    <path d="M16 19.2l2.9-3.3" stroke="#f4f3f0" strokeWidth="1.5" strokeLinecap="round" />
    <circle cx="18.9" cy="15.9" r="1.2" fill="#f4f3f0" />
  </svg>
)
