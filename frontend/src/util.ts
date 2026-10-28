import type { CircuitSpec, ModelCall, Spec } from './types'

export const pct = (p: number, digits = 1) => `${(p * 100).toFixed(digits)}%`

export function fmtRate(hz: number, unit = 'Hz'): string {
  if (!isFinite(hz) || hz <= 0) return `0 ${unit}`
  if (hz < 1e-3) return `${hz.toExponential(1)} ${unit}`
  if (hz < 1) return `${Number(hz.toPrecision(2))} ${unit}`
  const steps: [number, string][] = [[1e9, 'G'], [1e6, 'M'], [1e3, 'k'], [1, '']]
  for (const [f, p] of steps) {
    if (hz >= f) return `${Number((hz / f).toPrecision(3))} ${p}${unit}`
  }
  return `${hz.toExponential(2)} ${unit}`
}

export const clone = <T,>(x: T): T => JSON.parse(JSON.stringify(x)) as T

/** Human label of a model's provider, never claiming Meta for a mock answer. */
export function providerLabel(call: ModelCall): string {
  if (call.provider === 'meta') return call.cached ? 'Meta · cached' : 'Meta live'
  if (call.provider === 'mock-fallback') return 'Mock fallback'
  return 'Offline mock'
}

export function providerClass(call: ModelCall): string {
  return call.provider === 'meta' ? 'meta' : call.provider === 'mock-fallback' ? 'fallback' : 'mock'
}

export function parseIntList(text: string): number[] {
  return text.split(/[\s,]+/).filter(Boolean).map((t) => Number.parseInt(t, 10)).filter((n) => !Number.isNaN(n))
}

/** Angle text like "pi/4", "0.5", "-pi" -> radians, or null. */
export function parseAngle(text: string): number | null {
  const t = text.trim().toLowerCase().replace(/\s+/g, '').replace('π', 'pi')
  const m = t.match(/^(-?)(\d*\.?\d*)\*?pi(?:\/(\d+(?:\.\d+)?))?$/)
  if (m) {
    const sign = m[1] === '-' ? -1 : 1
    const k = m[2] === '' ? 1 : Number(m[2])
    const d = m[3] ? Number(m[3]) : 1
    return (sign * k * Math.PI) / d
  }
  const n = Number(t)
  return t !== '' && isFinite(n) ? n : null
}

export function angleText(theta: number): string {
  const f = theta / Math.PI
  for (const d of [1, 2, 3, 4, 6, 8, 12, 16]) {
    const k = Math.round(f * d)
    if (k !== 0 && Math.abs(f * d - k) < 1e-9) {
      const top = Math.abs(k) === 1 ? 'pi' : `${Math.abs(k)}pi`
      return `${k < 0 ? '-' : ''}${top}${d === 1 ? '' : `/${d}`}`
    }
  }
  return String(Number(theta.toFixed(6)))
}

export function specTitle(spec: Spec | null): string {
  return spec?.metadata?.title || (spec?.kind === 'network' ? 'Quantum network' : 'Quantum circuit')
}

/** Keep measurements consistent after the qubit count changes. */
export function resizeCircuit(spec: CircuitSpec, n: number): CircuitSpec {
  const next = clone(spec)
  const old = next.num_qubits
  next.num_qubits = n
  next.num_clbits = Math.max(n, 0)
  next.measurements = next.measurements.filter((m) => m.qubit < n && m.clbit < n)
  if (n > old) {
    const measuredAll = spec.measurements.length === old
    if (measuredAll) for (let q = old; q < n; q++) next.measurements.push({ qubit: q, clbit: q })
  }
  return next
}

export function downloadText(name: string, text: string) {
  const blob = new Blob([text], { type: 'text/plain' })
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = name
  a.click()
  URL.revokeObjectURL(a.href)
}

function toB64Url(bytes: Uint8Array): string {
  let bin = ''
  for (let i = 0; i < bytes.length; i += 0x8000) bin += String.fromCharCode(...bytes.subarray(i, i + 0x8000))
  return btoa(bin).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
}

function fromB64Url(text: string): Uint8Array {
  const bin = atob(text.replace(/-/g, '+').replace(/_/g, '/'))
  return Uint8Array.from(bin, (c) => c.charCodeAt(0))
}

async function pipe(bytes: Uint8Array, stream: CompressionStream | DecompressionStream): Promise<Uint8Array> {
  const out = new Blob([bytes as BlobPart]).stream().pipeThrough(stream)
  return new Uint8Array(await new Response(out).arrayBuffer())
}

/** Spec -> compact URL-safe text for a share link (photo boxes dropped: the receiver has no photo). */
export async function encodeSpec(spec: Spec): Promise<string> {
  const lean = JSON.parse(JSON.stringify(spec, (k, v) => (k === 'source' && v && typeof v === 'object' ? undefined : v)))
  const bytes = new TextEncoder().encode(JSON.stringify(lean))
  if (typeof CompressionStream !== 'undefined') return `z${toB64Url(await pipe(bytes, new CompressionStream('deflate-raw')))}`
  return `j${toB64Url(bytes)}`
}

export async function decodeSpec(text: string): Promise<Spec> {
  const raw = fromB64Url(text.slice(1))
  const bytes = text[0] === 'z' ? await pipe(raw, new DecompressionStream('deflate-raw')) : raw
  return JSON.parse(new TextDecoder().decode(bytes)) as Spec
}
