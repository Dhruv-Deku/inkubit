import { useRef, useState, type ReactNode } from 'react'
import type { Examples, RecentRun, Spec } from '../types'
import { CameraCapture } from './CameraCapture'
import { Upload } from './Icons'

const IDEAS = ['GHZ state on 4 qubits', 'Bernstein-Vazirani with secret 1011', 'QFT on 3 qubits of 5',
  'h 0; cx 0 1; rz pi/4 1', '300 km of fiber with 2 repeaters']

interface Props {
  examples: Examples | null
  busy: boolean
  error: string | null
  onImage: (file: Blob, name: string) => void
  onSpec: (spec: Spec) => void
  onText: (text: string) => void
  live: boolean
  recent: RecentRun[]
  onOpen: (id: string) => void
  extra?: ReactNode  // the challenge board
}

const BLANK: Spec = {
  kind: 'circuit', version: '1.0', num_qubits: 2, num_clbits: 2, operations: [],
  measurements: [{ qubit: 0, clbit: 0 }, { qubit: 1, clbit: 1 }], metadata: { title: 'My circuit', origin: 'manual' },
}

export function StartPanel({ examples, busy, error, onImage, onSpec, onText, live, recent, onOpen, extra }: Props) {
  const input = useRef<HTMLInputElement>(null)
  const [camera, setCamera] = useState(false)
  const [words, setWords] = useState('')
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
          <button className="btn small" style={{ marginTop: 10 }} disabled={busy}
            onClick={(e) => { e.stopPropagation(); setCamera(true) }}>Use the camera</button>
          <input ref={input} type="file" accept="image/*" hidden
            onChange={(e) => { const f = e.target.files?.[0]; if (f) onImage(f, f.name); e.target.value = '' }} />
        </div>
      </div>

      {camera && <CameraCapture onClose={() => setCamera(false)} onShot={(b) => { setCamera(false); onImage(b, 'camera.jpg') }} />}
      {error && <div className="notice error">{error}</div>}

      {recent.length > 0 && (
        <div className="panel">
          <div className="panel-head"><h2>Recent runs</h2><span className="sub">this session; click to reopen the log and results</span></div>
          <div className="spec-list">
            {recent.map((r) => (
              <button key={r.id} className="btn" onClick={() => onOpen(r.id)}>
                <span>{r.title}</span>
                <span className={`badge ${r.outcome === 'verified' || r.outcome === 'improved' ? 'pass' : r.outcome ? 'fail' : ''}`}>
                  {r.outcome ?? 'running'}
                </span>
                <span className="sub">{r.started}</span>
              </button>
            ))}
          </div>
        </div>
      )}

      <div className="panel">
        <div className="panel-head"><h2>Or describe it in words</h2>
          <span className="sub">{live ? 'Muse Spark turns any description into a spec' : 'offline: named algorithms, gate lists and simple networks'}</span>
        </div>
        <form className="row" style={{ gap: 10, alignItems: 'stretch' }}
          onSubmit={(e) => { e.preventDefault(); if (words.trim()) onText(words) }}>
          <input type="text" value={words} onChange={(e) => setWords(e.target.value)} style={{ flex: 1 }}
            placeholder="e.g. Grover search over 2 qubits, or: h 0; cx 0 1; measure all" aria-label="Describe a circuit or network" spellCheck={false} />
          <button className="btn primary" type="submit" disabled={busy || !words.trim()}>{busy ? 'Reading…' : 'Build it'}</button>
        </form>
        <div className="row wrap" style={{ gap: 6, marginTop: 10 }}>
          {IDEAS.map((t) => <button key={t} className="chip-btn" onClick={() => { setWords(t); onText(t) }} disabled={busy}>{t}</button>)}
        </div>
      </div>

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

      {extra}
      <div className="hero">
        <div className="panel">
          <div className="panel-head"><h2>Start from a spec</h2><span className="spacer" />
            <button className="btn small primary" onClick={() => onSpec(BLANK)} title="An empty two-qubit circuit: pick gates from the palette and click wires">
              Blank circuit
            </button>
          </div>
          {[...new Set(examples?.specs.map((s) => s.group) ?? [])].map((g) => (
            <div key={g} style={{ marginBottom: 12 }}>
              <div className="label" style={{ marginBottom: 6 }}>{g}</div>
              <div className="spec-list">
                {examples?.specs.filter((s) => s.group === g).map((s) => (
                  <button key={s.id} className="btn" onClick={() => onSpec(s.spec)} title={s.notes}>
                    {s.title}{!s.valid && <span className="badge warn">invalid on purpose</span>}
                  </button>
                ))}
              </div>
            </div>
          ))}
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
