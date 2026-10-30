import { useEffect, useRef, useState } from 'react'
import { api, ApiError } from '../api'
import type { ModelCall } from '../types'

interface Recognition {
  lang: string
  interimResults: boolean
  continuous: boolean
  onresult: ((e: { results: ArrayLike<ArrayLike<{ transcript: string }> & { isFinal: boolean }> }) => void) | null
  onerror: ((e: { error: string }) => void) | null
  onend: (() => void) | null
  start: () => void
  stop: () => void
}
type RecognitionCtor = new () => Recognition

function ctor(): RecognitionCtor | null {
  const w = window as unknown as { SpeechRecognition?: RecognitionCtor; webkitSpeechRecognition?: RecognitionCtor }
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null
}

const RATE = 16000
const MAX_SECONDS = 30

/** Average the mic's samples down to 16 kHz (a box filter is enough for speech). */
function downsample(chunks: Float32Array[], from: number): Float32Array {
  const total = chunks.reduce((n, c) => n + c.length, 0)
  const all = new Float32Array(total)
  let at = 0
  for (const c of chunks) { all.set(c, at); at += c.length }
  if (from === RATE) return all
  const step = from / RATE
  const out = new Float32Array(Math.floor(total / step))
  for (let i = 0; i < out.length; i++) {
    const a = Math.floor(i * step), b = Math.min(total, Math.floor((i + 1) * step))
    let sum = 0
    for (let j = a; j < b; j++) sum += all[j]
    out[i] = b > a ? sum / (b - a) : 0
  }
  return out
}

/** Mono 16-bit PCM WAV, the format Muse Voice Transcribe takes. */
function wav(samples: Float32Array): Blob {
  const buf = new ArrayBuffer(44 + samples.length * 2)
  const v = new DataView(buf)
  const str = (o: number, s: string) => { for (let i = 0; i < s.length; i++) v.setUint8(o + i, s.charCodeAt(i)) }
  str(0, 'RIFF'); v.setUint32(4, 36 + samples.length * 2, true); str(8, 'WAVE')
  str(12, 'fmt '); v.setUint32(16, 16, true); v.setUint16(20, 1, true); v.setUint16(22, 1, true)
  v.setUint32(24, RATE, true); v.setUint32(28, RATE * 2, true); v.setUint16(32, 2, true); v.setUint16(34, 16, true)
  str(36, 'data'); v.setUint32(40, samples.length * 2, true)
  for (let i = 0; i < samples.length; i++) {
    const s = Math.max(-1, Math.min(1, samples[i]))
    v.setInt16(44 + i * 2, s < 0 ? s * 0x8000 : s * 0x7fff, true)
  }
  return new Blob([buf], { type: 'audio/wav' })
}

interface Take { stop: () => Promise<Blob>; cancel: () => void }

/** Record the microphone until stopped; the level callback drives the meter. */
async function record(onLevel: (rms: number) => void): Promise<Take> {
  const stream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true } })
  const ctx = new AudioContext()
  const src = ctx.createMediaStreamSource(stream)
  const proc = ctx.createScriptProcessor(4096, 1, 1)
  const mute = ctx.createGain()
  mute.gain.value = 0
  const chunks: Float32Array[] = []
  proc.onaudioprocess = (e) => {
    const d = e.inputBuffer.getChannelData(0)
    chunks.push(new Float32Array(d))
    let s = 0
    for (let i = 0; i < d.length; i++) s += d[i] * d[i]
    onLevel(Math.sqrt(s / d.length))
  }
  src.connect(proc); proc.connect(mute); mute.connect(ctx.destination)
  const close = () => {
    proc.onaudioprocess = null
    src.disconnect(); proc.disconnect(); mute.disconnect()
    stream.getTracks().forEach((t) => t.stop())
    void ctx.close()
  }
  return {
    stop: async () => { const rate = ctx.sampleRate; close(); return wav(downsample(chunks, rate)) },
    cancel: close,
  }
}

type Phase = 'idle' | 'listening' | 'reading'

/**
 * Speak a description instead of typing it. Live, the browser records a WAV and Muse Voice Transcribe turns it into
 * text; offline, the browser's own speech recognition is used (hidden where the browser has none).
 */
export function VoiceButton({ onText, onDone, disabled, live }: { onText: (t: string) => void; onDone: (t: string, voice?: ModelCall) => void; disabled?: boolean; live?: boolean }) {
  const [phase, setPhase] = useState<Phase>('idle')
  const [error, setError] = useState<string | null>(null)
  const [note, setNote] = useState<string | null>(null)
  const [level, setLevel] = useState(0)
  const [secs, setSecs] = useState(0)
  const rec = useRef<Recognition | null>(null)
  const take = useRef<Take | null>(null)
  const timer = useRef<number | null>(null)
  const heard = useRef('')
  useEffect(() => () => { rec.current?.stop(); take.current?.cancel(); if (timer.current) clearInterval(timer.current) }, [])
  const Ctor = typeof window !== 'undefined' ? ctor() : null
  const canRecord = typeof navigator !== 'undefined' && !!navigator.mediaDevices?.getUserMedia && typeof AudioContext !== 'undefined'
  const useMuse = !!live && canRecord
  if (!useMuse && !Ctor) return null

  const browserStart = () => {
    heard.current = ''
    const r = new Ctor!()
    r.lang = navigator.language || 'en-US'
    r.interimResults = true
    r.continuous = false
    r.onresult = (e) => {
      const text = Array.from(e.results).map((res) => res[0].transcript).join(' ').trim()
      heard.current = text
      onText(text)
    }
    r.onerror = (e) => setError(e.error === 'not-allowed' ? 'Microphone access was blocked.' : `Speech recognition: ${e.error}`)
    r.onend = () => {
      setPhase('idle')
      if (heard.current) onDone(heard.current)
    }
    rec.current = r
    r.start()
    setPhase('listening')
  }

  const finish = async () => {
    if (timer.current) { clearInterval(timer.current); timer.current = null }
    const t = take.current
    take.current = null
    if (!t) return
    setPhase('reading')
    setLevel(0)
    try {
      const out = await api.transcribe(await t.stop())
      onText(out.text)
      setNote(`heard by ${out.call.model} · ${out.call.cached ? 'cached' : `${out.call.latency_s.toFixed(1)} s`}`)
      onDone(out.text, out.call)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Transcription failed.')
    } finally {
      setPhase('idle')
    }
  }

  const museStart = async () => {
    try {
      take.current = await record((rms) => setLevel(Math.min(1, rms * 6)))
    } catch (err) {
      setError((err as Error).name === 'NotAllowedError' ? 'Microphone access was blocked.' : 'No microphone was found.')
      return
    }
    const t0 = performance.now()
    setSecs(0)
    timer.current = window.setInterval(() => {
      const s = (performance.now() - t0) / 1000
      setSecs(Math.floor(s))
      if (s >= MAX_SECONDS) void finish()
    }, 250)
    setPhase('listening')
  }

  const click = () => {
    if (phase === 'listening') {
      if (useMuse) void finish()
      else rec.current?.stop()
      return
    }
    setError(null)
    setNote(null)
    if (useMuse) void museStart()
    else browserStart()
  }

  const label = phase === 'reading' ? 'Reading…' : phase === 'listening' ? (useMuse ? `Stop · ${secs} s` : 'Listening…') : 'Say it'
  return (
    <>
      <button type="button" className={`btn mic ${phase === 'listening' ? 'on' : ''}`} disabled={disabled || phase === 'reading'}
        onClick={click} aria-pressed={phase === 'listening'}
        title={useMuse ? 'Say it instead: Muse Voice Transcribe turns your words into text' : "Say it instead: your browser's speech recognition turns it into text"}
        aria-label={phase === 'listening' ? 'Stop and transcribe' : 'Describe it by voice'}>
        <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden>
          <rect x="5.5" y="1.5" width="5" height="8.5" rx="2.5" stroke="currentColor" strokeWidth="1.5" />
          <path d="M3 8a5 5 0 0010 0M8 13v2" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
        </svg>
        {label}
        {useMuse && phase === 'listening' && <span className="mic-level" aria-hidden><span style={{ transform: `scaleY(${0.15 + 0.85 * level})` }} /></span>}
      </button>
      {error && <span className="sub" style={{ color: '#ffb3b5', alignSelf: 'center' }}>{error}</span>}
      {!error && note && <span className="sub mono" style={{ alignSelf: 'center' }}>{note}</span>}
    </>
  )
}
