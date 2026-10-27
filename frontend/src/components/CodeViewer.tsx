import { useState } from 'react'
import type { Attempt } from '../types'
import { downloadText } from '../util'
import { Copy } from './Icons'

export function DiffView({ diff }: { diff: string }) {
  return (
    <pre className="diff">
      {diff.split('\n').map((line, i) => {
        const cls = line.startsWith('+++') || line.startsWith('---') ? 'hunk'
          : line.startsWith('+') ? 'add' : line.startsWith('-') ? 'del' : line.startsWith('@@') ? 'hunk' : ''
        return <span key={i} className={cls}>{line || ' '}{'\n'}</span>
      })}
    </pre>
  )
}

/** Code of every attempt, with copy/download and the diff each repair made. */
export function CodeViewer({ attempts, finalCode }: { attempts: Attempt[]; finalCode: string }) {
  const [tab, setTab] = useState(attempts.length - 1)
  const [view, setView] = useState<'code' | 'diff'>('code')
  const [copied, setCopied] = useState(false)
  const current = attempts[tab]
  const code = current?.code ?? finalCode
  const copy = async () => {
    await navigator.clipboard.writeText(code)
    setCopied(true)
    setTimeout(() => setCopied(false), 1400)
  }
  return (
    <div>
      <div className="tabs">
        {attempts.map((a, i) => (
          <button key={a.attempt} className={i === tab ? 'on' : ''} onClick={() => { setTab(i); if (!a.diff_from_previous) setView('code') }}>
            Attempt {a.attempt} · {a.passed ? 'verified' : 'failed'}
          </button>
        ))}
      </div>
      <div className="row" style={{ marginBottom: 8 }}>
        {current?.diff_from_previous && (
          <div className="seg">
            <button className={view === 'code' ? 'on' : ''} onClick={() => setView('code')}>Code</button>
            <button className={view === 'diff' ? 'on' : ''} onClick={() => setView('diff')}>Changes from attempt {current.attempt - 1}</button>
          </div>
        )}
        <span className="grow" />
        <button className="btn small" onClick={copy}><Copy />{copied ? 'Copied' : 'Copy'}</button>
        <button className="btn small" onClick={() => downloadText(`qcanvas_attempt_${current?.attempt ?? 'final'}.py`, code)}>Download .py</button>
      </div>
      {current?.diagnosis && !current.passed && (
        <div className="notice error" style={{ marginBottom: 8 }}>
          <strong>Why it failed:</strong> {current.diagnosis.summary}. {current.diagnosis.hint}.
          {current.fix_summary && <div style={{ marginTop: 4 }}><strong>Fix applied next:</strong> {current.fix_summary}</div>}
        </div>
      )}
      {view === 'diff' && current?.diff_from_previous ? <DiffView diff={current.diff_from_previous} /> : <pre className="code">{code}</pre>}
    </div>
  )
}
