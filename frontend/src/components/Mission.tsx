import { useEffect, useMemo, useRef, useState } from 'react'
import { api, ApiError } from '../api'
import type { CircuitSpec, CopilotTool, Examples, MissionNode, MissionReport } from '../types'
import { CallBadge } from './CallBadge'
import { ToolCard, TraceBadge } from './Copilot'
import { VoiceButton } from './VoiceButton'

const SAMPLES: { label: string; goal: string; photo?: string }[] = [
  { label: 'Secure two cities', goal: 'Connect two cities 1,200 km apart with quantum-secure keys: compare a satellite with fiber, find the best fix, and check whether a spy listening to 25% of the photons would be caught.' },
  { label: 'Photo to hardware', photo: 'ghz', goal: "Read the circuit in this photo, find a shorter version that is proven equal, and check how well it survives today's hardware." },
  { label: 'Break a molecule', goal: 'Map how the hydrogen molecule breaks: energies at 0.74 Å, 1.5 Å and 2.5 Å, where the classical shortcut fails, and how much error mitigation recovers.' },
  { label: 'Is RSA exposed?', goal: "How exposed is RSA today? Factor 15 with Shor's algorithm for two bases, and compare with Grover search on 3 qubits under realistic noise." },
  { label: 'Schedule exams', goal: 'Six exams with clashes Maths-Physics, Physics-Chemistry, Chemistry-Biology, Biology-Maths, History-Art, Maths-History: put them on two days so no clashing pair shares a day, and check how QAOA does on real hardware.' },
]

const STATUS: Record<MissionNode['status'], string> = {
  waiting: 'waiting', running: 'running', verifying: 'verifying', done: 'verified', repaired: 'repaired, verified',
  flagged: 'flagged', failed: 'failed', skipped: 'skipped',
}
const ICON: Record<MissionNode['status'], string> = {
  waiting: '○', running: '◐', verifying: '◑', done: '✓', repaired: '✓', flagged: '⚠', failed: '✕', skipped: '–',
}
const LANE_TITLE = ['Perceive', 'Plan', 'Run and verify', 'Report']

/** Columns by dependency depth; rows in arrival order. */
function layout(nodes: MissionNode[]) {
  const byId = new Map(nodes.map((n) => [n.id, n]))
  const depth = new Map<string, number>()
  const d = (n: MissionNode, seen = new Set<string>()): number => {
    if (depth.has(n.id)) return depth.get(n.id)!
    if (seen.has(n.id)) return 0
    seen.add(n.id)
    const parents = n.after.map((a) => byId.get(a)).filter((p): p is MissionNode => !!p)
    const v = n.lane === 'perceive' ? 0 : parents.length ? 1 + Math.max(...parents.map((p) => d(p, seen))) : n.lane === 'plan' ? 0 : 1
    depth.set(n.id, v)
    return v
  }
  nodes.forEach((n) => d(n))
  const cols: MissionNode[][] = []
  nodes.forEach((n) => { const c = depth.get(n.id)!; (cols[c] ??= []).push(n) })
  return cols.map((c) => c ?? [])
}

const NW = 196, NH = 70, CW = 228, RH = 84, PAD = 8

function Graph({ nodes, selected, onSelect }: { nodes: MissionNode[]; selected: string | null; onSelect: (id: string) => void }) {
  const cols = layout(nodes)
  const pos = new Map<string, { x: number; y: number }>()
  const tallest = Math.max(1, ...cols.map((c) => c.length))
  cols.forEach((c, i) => c.forEach((n, j) => pos.set(n.id, { x: PAD + i * CW, y: PAD + j * RH + ((tallest - c.length) * RH) / 2 })))
  const W = PAD * 2 + Math.max(1, cols.length) * CW - (CW - NW), H = PAD * 2 + tallest * RH - (RH - NH)
  const byId = new Map(nodes.map((n) => [n.id, n]))
  return (
    <div className="mission-graph-scroll">
      <div className="mission-graph" style={{ width: W, height: H }}>
        <svg width={W} height={H} aria-hidden>
          {nodes.flatMap((n) => n.after.map((a) => {
            const p = pos.get(a), q = pos.get(n.id)
            if (!p || !q) return null
            const x1 = p.x + NW, y1 = p.y + NH / 2, x2 = q.x, y2 = q.y + NH / 2, mx = (x1 + x2) / 2
            const live = n.status === 'running' || n.status === 'verifying'
            const from = byId.get(a)
            return <path key={`${a}-${n.id}`} d={`M${x1} ${y1} C${mx} ${y1} ${mx} ${y2} ${x2} ${y2}`} fill="none"
              stroke={live ? 'var(--primary)' : from && ['done', 'repaired'].includes(from.status) ? 'var(--text-2)' : 'var(--line-2)'}
              strokeWidth={live ? 2 : 1.5} strokeDasharray={n.status === 'waiting' ? '4 4' : undefined} className={live ? 'medge-flow' : undefined} />
          }))}
        </svg>
        {nodes.map((n) => {
          const p = pos.get(n.id)!
          const real = n.checks.filter((c) => c.affects)
          const ok = real.filter((c) => c.ok).length
          const mlMiss = n.checks.some((c) => !c.affects && !c.ok)
          return (
            <button key={n.id} className={`mnode s-${n.status}${selected === n.id ? ' sel' : ''}`} style={{ left: p.x, top: p.y, width: NW, height: NH }}
              onClick={() => onSelect(n.id)} aria-label={`${n.label}: ${STATUS[n.status]}`} title={n.purpose || n.detail || n.label}>
              <span className="mnode-top"><span className="mnode-icon" aria-hidden>{ICON[n.status]}</span><span className="mnode-label">{n.lane === 'step' ? n.purpose || n.label : n.label}</span></span>
              <span className="mnode-sub">{n.lane === 'step' ? n.label : n.model ?? ''}</span>
              <span className="mnode-sub">{STATUS[n.status]}{real.length ? ` · ${ok}/${real.length} checks` : ''}{mlMiss ? ' · ML missed' : ''}{n.seconds ? ` · ${n.seconds.toFixed(1)} s` : ''}</span>
            </button>
          )
        })}
      </div>
    </div>
  )
}

function Detail({ node, onOpen }: { node: MissionNode; onOpen?: (s: CircuitSpec) => void }) {
  const run: CopilotTool | null = node.lane === 'step' && node.tool
    ? { name: node.tool, args: node.args, facts: node.facts, card: node.card, error: node.status === 'failed' ? node.detail : null, seconds: node.seconds }
    : null
  return (
    <div className="mission-detail">
      <div className="row wrap" style={{ gap: 8 }}>
        <b>{node.lane === 'step' ? node.purpose || node.label : node.label}</b>
        <span className={`mstatus s-${node.status}`}>{ICON[node.status]} {STATUS[node.status]}</span>
        {node.model && <span className="sub mono">{node.model}</span>}
      </div>
      {node.detail && node.status !== 'failed' && <p className="sub" style={{ margin: '6px 0 0' }}>{node.detail}</p>}
      {node.checks.length > 0 && (
        <ul className="mission-checks">
          {node.checks.map((c) => (
            <li key={c.name} className={c.ok ? 'ok' : c.affects ? 'bad' : 'note'}><span aria-hidden>{c.ok ? '✓' : '⚠'}</span> <b>{c.name}</b>: {c.detail}
              {!c.affects && !c.ok && <span className="sub"> (grades the ML model; the step reports the exact value)</span>}</li>
          ))}
        </ul>
      )}
      {run && (node.card || run.error) && <ToolCard run={run} first onOpen={onOpen} />}
    </div>
  )
}

/** Mission control: a whole problem in words, a photo and speech; Muse Spark plans a graph of exact tools, which runs
 *  live in parallel; every result is verified, and the report's numbers are traced. */
export function MissionPanel({ live, examples, onOpen }: { live: boolean; examples: Examples | null; onOpen?: (s: CircuitSpec) => void }) {
  const [goal, setGoal] = useState('')
  const [photo, setPhoto] = useState<{ blob: Blob; url: string; name: string } | null>(null)
  const [transcript, setTranscript] = useState('')
  const [deep, setDeep] = useState(false)
  const [nodes, setNodes] = useState<MissionNode[]>([])
  const [report, setReport] = useState<MissionReport | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [selected, setSelected] = useState<string | null>(null)
  const [missionId, setMissionId] = useState<string | null>(null)
  const [elapsed, setElapsed] = useState(0)
  const source = useRef<EventSource | null>(null)
  const fileRef = useRef<HTMLInputElement | null>(null)
  useEffect(() => () => source.current?.close(), [])
  useEffect(() => {
    if (!busy) return
    const t0 = performance.now()
    const id = window.setInterval(() => setElapsed((performance.now() - t0) / 1000), 100)
    return () => window.clearInterval(id)
  }, [busy])

  const setImage = (blob: Blob, name: string) => {
    if (photo) URL.revokeObjectURL(photo.url)
    setPhoto({ blob, url: URL.createObjectURL(blob), name })
  }
  const sample = async (s: (typeof SAMPLES)[number]) => {
    setGoal(s.goal)
    setTranscript('')
    if (s.photo) {
      const img = examples?.images.find((i) => i.id.includes(s.photo!)) ?? examples?.images[0]
      if (img) setImage(await (await fetch(img.url)).blob(), img.title)
    } else if (photo) {
      URL.revokeObjectURL(photo.url)
      setPhoto(null)
    }
  }
  const launch = async (text?: string) => {
    const g = (text ?? goal).trim()
    if (!g || busy) return
    source.current?.close()
    setNodes([]); setReport(null); setError(null); setSelected(null); setBusy(true); setElapsed(0)
    try {
      const { mission_id } = await api.startMission(g, { image: text ? null : photo?.blob, transcript: text ? '' : transcript, deep: live && deep })
      setMissionId(mission_id)
      const es = new EventSource(`/api/missions/${mission_id}/events`)
      source.current = es
      es.addEventListener('mission', (ev) => {
        const d = JSON.parse((ev as MessageEvent).data) as { kind: string; node?: MissionNode; report?: MissionReport }
        if (d.kind === 'node' && d.node) {
          const n = d.node
          setNodes((ns) => (ns.some((x) => x.id === n.id) ? ns.map((x) => (x.id === n.id ? n : x)) : [...ns, n]))
        } else if (d.kind === 'report' && d.report) {
          setReport(d.report)
        }
      })
      es.addEventListener('end', (ev) => {
        const d = JSON.parse((ev as MessageEvent).data) as { status: string; error: string | null }
        if (d.error) setError(d.error)
        es.close(); setBusy(false)
      })
      es.onerror = () => { es.close(); setBusy(false) }
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'The mission could not start.')
      setBusy(false)
    }
  }
  useEffect(() => {  // the guided tour launches a sample mission
    const onTour = (e: Event) => {
      const d = (e as CustomEvent<{ action: string; sample?: string }>).detail
      const s = SAMPLES.find((x) => x.label === d.sample)
      if (d.action !== 'mission' || !s || s.photo) return
      setGoal(s.goal)
      if (photo) { URL.revokeObjectURL(photo.url); setPhoto(null) }
      void launch(s.goal)
    }
    window.addEventListener('inkubit:tour', onTour)
    return () => window.removeEventListener('inkubit:tour', onTour)
  })
  const steps = nodes.filter((n) => n.lane === 'step')
  const sel = useMemo(() => nodes.find((n) => n.id === selected) ?? null, [nodes, selected])
  return (
    <div className="panel mission">
      <div className="panel-head">
        <h2>Mission control</h2>
        <span className="sub">{live ? 'a whole problem in words, a photo or your voice: Muse Spark plans a graph of exact tools, it runs live in parallel, every result is verified twice'
          : 'offline: a keyword planner builds the graph; with a key Muse Spark plans it and writes the report'}</span>
      </div>
      <textarea className="mission-goal" rows={3} value={goal} onChange={(e) => setGoal(e.target.value)} disabled={busy}
        placeholder="Describe a whole problem: two cities to secure, a molecule to map, a circuit photo to make hardware-ready…" aria-label="Mission" />
      <div className="row wrap" style={{ gap: 8, marginTop: 8 }}>
        <input ref={fileRef} type="file" accept="image/*" capture="environment" hidden
          onChange={(e) => { const f = e.target.files?.[0]; if (f) setImage(f, f.name); e.target.value = '' }} />
        <button className="btn" onClick={() => fileRef.current?.click()} disabled={busy}>{photo ? 'Change photo' : 'Add a photo'}</button>
        <VoiceButton onText={(t) => { setGoal(t); setTranscript(t) }} onDone={(t) => { setGoal(t); setTranscript(t) }} disabled={busy} live={live} />
        {live && (
          <div className="seg" role="group" aria-label="Planner model">
            <button type="button" className={deep ? '' : 'on'} aria-pressed={!deep} onClick={() => setDeep(false)} disabled={busy}>Muse Spark</button>
            <button type="button" className={deep ? 'on' : ''} aria-pressed={deep} onClick={() => setDeep(true)} disabled={busy}
              title="Muse Wonder plans: slower, for harder problems">Muse Wonder</button>
          </div>
        )}
        <span className="spacer" />
        <button className="btn primary" onClick={() => { void launch() }} disabled={busy || !goal.trim()}>{busy ? `Running… ${elapsed.toFixed(1)} s` : 'Launch mission'}</button>
      </div>
      {photo && (
        <div className="mission-photo">
          <img src={photo.url} alt="The photo for this mission" />
          <span className="sub">{photo.name}</span>
          <button className="chip-btn" onClick={() => { URL.revokeObjectURL(photo.url); setPhoto(null) }} disabled={busy}>Remove</button>
        </div>
      )}
      {!nodes.length && !busy && (
        <div className="row wrap" style={{ gap: 6, marginTop: 10 }}>
          <span className="label">Samples</span>
          {SAMPLES.map((s) => <button key={s.label} className="chip-btn" onClick={() => { void sample(s) }}>{s.label}</button>)}
        </div>
      )}
      {error && <div className="notice error" style={{ marginTop: 10 }}>{error}</div>}
      {nodes.length > 0 && (
        <>
          <div className="row wrap mission-lanes" aria-hidden>{LANE_TITLE.map((t) => <span key={t} className="label">{t}</span>)}</div>
          <Graph nodes={nodes} selected={selected} onSelect={(id) => setSelected((s) => (s === id ? null : id))} />
          <div className="sub" aria-live="polite" style={{ marginTop: 4 }}>
            {steps.length ? `${steps.filter((n) => ['done', 'repaired'].includes(n.status)).length} of ${steps.length} steps verified` : 'planning…'}
            {steps.some((n) => n.status === 'flagged') ? ` · ${steps.filter((n) => n.status === 'flagged').length} flagged` : ''}
            {steps.some((n) => n.status === 'failed') ? ` · ${steps.filter((n) => n.status === 'failed').length} failed` : ''}
            {' · click a step to see its result and checks'}
          </div>
        </>
      )}
      {sel && <Detail node={sel} onOpen={onOpen} />}
      {report && (
        <div className="mission-report">
          <p className="mission-headline">{report.headline}</p>
          <ul>{report.findings.map((f, i) => <li key={i}>{f}</li>)}</ul>
          {report.next && <p className="sub">{report.next}</p>}
          <div className="row wrap" style={{ gap: 8 }}>
            <TraceBadge trace={report.trace} />
            <span className="trace-badge">{report.verified} verified{report.flagged ? ` · ${report.flagged} flagged` : ''}</span>
            {missionId && !busy && <a className="btn small" href={`/api/missions/${missionId}/report`} download>Download report</a>}
            {report.calls.map((c, i) => <CallBadge key={i} call={c} />)}
            <span className="sub">{report.router === 'muse' ? 'planned and written by Muse' : 'offline planner'} · {report.seconds.toFixed(1)} s</span>
          </div>
        </div>
      )}
    </div>
  )
}
