import { useEffect, useRef, useState } from 'react'

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

/**
 * Speak a description instead of typing it. Uses the browser's own speech recognition (which may send audio to the
 * browser maker's service); hidden where the browser has none.
 */
export function VoiceButton({ onText, onDone, disabled }: { onText: (t: string) => void; onDone: (t: string) => void; disabled?: boolean }) {
  const [listening, setListening] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const rec = useRef<Recognition | null>(null)
  const heard = useRef('')
  useEffect(() => () => rec.current?.stop(), [])
  const Ctor = typeof window !== 'undefined' ? ctor() : null
  if (!Ctor) return null
  const start = () => {
    setError(null)
    heard.current = ''
    const r = new Ctor()
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
      setListening(false)
      if (heard.current) onDone(heard.current)
    }
    rec.current = r
    r.start()
    setListening(true)
  }
  return (
    <>
      <button type="button" className={`btn mic ${listening ? 'on' : ''}`} disabled={disabled}
        onClick={() => (listening ? rec.current?.stop() : start())}
        title="Say it instead: your browser's speech recognition turns it into text" aria-pressed={listening}
        aria-label={listening ? 'Stop listening' : 'Describe it by voice'}>
        <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden>
          <rect x="5.5" y="1.5" width="5" height="8.5" rx="2.5" stroke="currentColor" strokeWidth="1.5" />
          <path d="M3 8a5 5 0 0010 0M8 13v2" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
        </svg>
        {listening ? 'Listening…' : 'Say it'}
      </button>
      {error && <span className="sub" style={{ color: '#ffb3b5', alignSelf: 'center' }}>{error}</span>}
    </>
  )
}
