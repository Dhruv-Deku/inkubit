import { useEffect, useRef, useState } from 'react'

export type TourSection = 'build' | 'discover' | 'hardware' | 'labs' | 'evidence' | null

interface Step {
  section: TourSection  // null: the top of the page (Mission control)
  panel: string  // heading the step scrolls to
  title: string
  text: string
  seconds: number
  action?: { action: string; sample?: string; goal?: string }
}

/** Every number here is one the app computes on the page the step shows. */
const STEPS: Step[] = [
  { section: null, panel: 'Mission control', title: 'Mission control', seconds: 12,
    action: { action: 'mission', sample: 'Secure two cities' },
    text: 'One request in words, a photo or speech. Muse Spark plans a graph of exact tools, independent steps run in parallel, every result passes physics checks and two independent simulators, and every number in the report is traced. A real mission is starting now.' },
  { section: 'evidence', panel: 'AI alone vs Inkubit', title: 'Why verify at all?', seconds: 9,
    text: 'Asked alone, the same model was exact on small circuits but on only 3 of 6 bigger ones, once 43% off with full confidence. So Inkubit never shows a number nothing checked.' },
  { section: 'discover', panel: 'Discovery lab', title: 'AI proposes, physics proves', seconds: 11,
    action: { action: 'discovery', goal: 'ghz7_hex' },
    text: 'Muse Spark proposes circuit layouts for a GHZ state on all 7 qubits of an IBM heavy-hex chip; an exact optimiser fits them and Qiskit proves each winner. The search is running; we come back for the result.' },
  { section: 'hardware', panel: 'ML error-correction decoder', title: 'A learned decoder', seconds: 9,
    text: 'On the distance-3 surface code, a network that reads both kinds of checks makes about a fifth fewer logical errors than minimum-weight matching, beyond the error bars at every noise level.' },
  { section: 'hardware', panel: 'Code lab', title: 'Codes designed by AI, proven exactly', seconds: 9,
    text: 'Muse Spark designs error-correcting codes and an exact checker proves each one. For hardware where phase flips dominate, it found a 9-qubit code that needs 9 phase-flip errors to fail, three times the surface code, while still correcting any single error.' },
  { section: 'hardware', panel: 'Pulse lab', title: 'Down to the microwave pulse', seconds: 9,
    text: 'The X gate as the pulse that drives a three-level transmon: plain Gaussians leak into |2⟩ when fast; DRAG reaches about 1e-4 error at 15 ns, limited only by T1 and T2.' },
  { section: 'hardware', panel: 'Satellite planner', title: 'Out to orbit, live', seconds: 10,
    text: 'The quantum-key satellites in orbit today, on their real orbits from today’s CelesTrak elements: where SpeQtre is right now, every night pass over its ground stations and the cloud forecast for each. Micius re-entered in January 2026; its 2017 experiments replay on a model.' },
  { section: 'discover', panel: 'When does quantum win?', title: 'Honest about advantage', seconds: 9,
    text: 'Surface-code estimates against the best classical route, checked against the published RSA-2048 figure. For brute-force search on 64-bit keys, it says plainly: classical wins.' },
  { section: 'discover', panel: 'Discovery lab', title: 'What the search found', seconds: 10,
    text: 'The textbook GHZ circuit, compiled onto the chip, needs 10 CNOTs; the discovered one needs 6, proven exact by Qiskit, and keeps more of the state under realistic noise.' },
  { section: 'evidence', panel: 'Real hardware', title: 'On a real quantum computer', seconds: 10,
    text: 'Both GHZ circuits then ran on IBM’s ibm_fez, on the same seven qubits: the discovered one reached a GHZ fidelity of 0.814 against 0.795, 3.2 standard errors apart, and both certify genuine 7-qubit entanglement. A noise preset calibrated from the chip predicts its counts closer than a digital twin did.' },
  { section: 'build', panel: 'Live board', title: 'Point, draw, see', seconds: 9,
    text: 'Point a camera at a whiteboard: when the drawing changes and holds still, SAM 3.1 and Muse Spark read it and the odds appear on the wires. The original pipeline, sketch to verified code with a self-repair agent, is right above.' },
  { section: null, panel: 'Mission control', title: 'Back to the mission', seconds: 10,
    text: 'The mission from the start: its plan, the checks on every step and a report whose numbers are all traced to exact tools. Everything else is one tab away.' },
]

/** A guided tour of about 95 seconds for people with little time: each step opens a section, highlights a panel
 *  and says what it shows; two steps start real runs so their results are ready when the tour returns. */
export function Tour({ onGo, onClose }: { onGo: (section: TourSection, panel: string) => void; onClose: () => void }) {
  const [i, setI] = useState(0)
  const [playing, setPlaying] = useState(true)
  const [left, setLeft] = useState(STEPS[0].seconds)
  const fired = useRef(new Set<number>())
  const step = STEPS[i]
  useEffect(() => {
    onGo(step.section, step.panel)
    setLeft(step.seconds)
    if (step.action && !fired.current.has(i)) {
      fired.current.add(i)
      const a = step.action
      window.setTimeout(() => window.dispatchEvent(new CustomEvent('inkubit:tour', { detail: a })), 600)
    }
  }, [i]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!playing) return
    const id = window.setInterval(() => setLeft((s) => {
      if (s > 1) return s - 1
      setI((k) => (k + 1 < STEPS.length ? k + 1 : k))
      return 0
    }), 1000)
    return () => window.clearInterval(id)
  }, [playing])
  useEffect(() => { if (i === STEPS.length - 1 && left === 0) setPlaying(false) }, [i, left])
  return (
    <div className="tour" role="dialog" aria-label="Guided tour">
      <div className="row" style={{ gap: 8 }}>
        <span className="label">Tour {i + 1} / {STEPS.length}</span>
        <span className="spacer" />
        <button className="chip-btn" onClick={onClose} aria-label="End the tour">End</button>
      </div>
      <div className="tour-bar"><span style={{ width: `${((i + (step.seconds - left) / step.seconds) / STEPS.length) * 100}%` }} /></div>
      <b className="tour-title">{step.title}</b>
      <p className="tour-text" aria-live="polite">{step.text}</p>
      <div className="row" style={{ gap: 6 }}>
        <button className="btn small" onClick={() => setI((k) => Math.max(0, k - 1))} disabled={i === 0}>Back</button>
        <button className="btn small" onClick={() => setPlaying((p) => !p)}>{playing ? 'Pause' : 'Play'}</button>
        <button className="btn small primary" onClick={() => (i + 1 < STEPS.length ? setI(i + 1) : onClose())}>{i + 1 < STEPS.length ? 'Next' : 'Done'}</button>
        <span className="spacer" />
        {playing && <span className="sub mono">{left}s</span>}
      </div>
    </div>
  )
}
