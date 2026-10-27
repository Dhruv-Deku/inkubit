import { useRef, useState } from 'react'
import type { Examples, Spec } from '../types'
import { Upload } from './Icons'

interface Props {
  examples: Examples | null
  busy: boolean
  error: string | null
  onImage: (file: Blob, name: string) => void
  onSpec: (spec: Spec) => void
}

export function StartPanel({ examples, busy, error, onImage, onSpec }: Props) {
  const input = useRef<HTMLInputElement>(null)
  const [over, setOver] = useState(false)
  const [paste, setPaste] = useState('')
  const [pasteError, setPasteError] = useState<string | null>(null)

  const pickSample = async (url: string, id: string) => {
    const blob = await (await fetch(url)).blob()
    onImage(blob, `${id}.png`)
  }

  const usePaste = () => {
    try {
      const data = JSON.parse(paste)
      if (!data || typeof data !== 'object' || !('kind' in data)) throw new Error('missing "kind"')
      setPasteError(null)
      onSpec(data as Spec)
    } catch (e) {
      setPasteError(`That is not a spec: ${(e as Error).message}`)
    }
  }

  return (
    <div className="stack">
      <div className="hero">
        <div className="panel hero-copy">
          <h2>From a pencil sketch to verified quantum code.</h2>
          <p>
            Photograph a hand-drawn circuit or a satellite network. Q-Canvas reads it, writes the Qiskit code,
            runs it under realistic noise, and checks the answer against an independent simulation. When the
            code is wrong, you watch the agent find the bug and fix it.
          </p>
          <div className="pipeline">
            <span>SAM 3.1 finds the drawn parts</span>
            <span>Muse Spark reads the sketch</span>
            <span>You correct the spec</span>
            <span>Agent writes, runs, verifies, repairs</span>
            <span>Muse Spark explains</span>
            <span>Muse Image draws it clean</span>
          </div>
        </div>
        <div
          className={`drop ${over ? 'over' : ''}`}
          role="button"
          tabIndex={0}
          onClick={() => input.current?.click()}
          onKeyDown={(e) => e.key === 'Enter' && input.current?.click()}
          onDragOver={(e) => { e.preventDefault(); setOver(true) }}
          onDragLeave={() => setOver(false)}
          onDrop={(e) => {
            e.preventDefault()
            setOver(false)
            const f = e.dataTransfer.files[0]
            if (f) onImage(f, f.name)
          }}
        >
          {busy ? <div className="spin" style={{ width: 26, height: 26 }} /> : <Upload />}
          <strong>{busy ? 'Reading your sketch…' : 'Drop a photo of your sketch'}</strong>
          <span className="sub">or click to choose a file (PNG, JPG, up to 15 MB)</span>
          <input ref={input} type="file" accept="image/*" hidden
            onChange={(e) => { const f = e.target.files?.[0]; if (f) onImage(f, f.name); e.target.value = '' }} />
        </div>
      </div>

      {error && <div className="notice error">{error}</div>}

      <div className="panel">
        <div className="panel-head"><h2>Sample sketches</h2><span className="sub">photos of pen drawings, bundled for offline demos</span></div>
        <div className="samples">
          {examples?.images.map((img) => (
            <button key={img.id} className="sample" disabled={busy} onClick={() => pickSample(img.url, img.id)}>
              <img src={img.url} alt={img.title} />
              <div><span>{img.title}</span><span className="badge">{img.kind}</span></div>
            </button>
          ))}
        </div>
      </div>

      <div className="hero">
        <div className="panel">
          <div className="panel-head"><h2>Start from a spec</h2></div>
          <div className="spec-list">
            {examples?.specs.map((s) => (
              <button key={s.id} className="btn" onClick={() => onSpec(s.spec)} title={s.notes}>
                {s.title}{!s.valid && <span className="badge warn">invalid on purpose</span>}
              </button>
            ))}
          </div>
        </div>
        <div className="panel">
          <div className="panel-head"><h2>Paste JSON</h2><span className="spacer" />
            <button className="btn small" disabled={!paste.trim()} onClick={usePaste}>Use this spec</button>
          </div>
          <textarea rows={5} value={paste} onChange={(e) => setPaste(e.target.value)}
            placeholder='{"kind": "circuit", "num_qubits": 2, ...}' />
          {pasteError && <div className="notice error" style={{ marginTop: 8 }}>{pasteError}</div>}
        </div>
      </div>
    </div>
  )
}
