import type { ModelCall } from '../types'
import { providerClass, providerLabel } from '../util'

/** "muse-spark-1.3 · Meta live" chip; mock answers are always labelled as mock. */
export function CallBadge({ call, showModel = true }: { call: ModelCall; showModel?: boolean }) {
  const title = call.error ? `Live call failed, mock answered instead: ${call.error}` : `${call.role} · ${call.latency_s.toFixed(1)} s`
  return (
    <span className={`badge ${providerClass(call)}`} title={title}>
      <span className="dot" />
      {showModel ? `${call.model} · ` : ''}
      {providerLabel(call)}
    </span>
  )
}

export function CallsTable({ calls }: { calls: ModelCall[] }) {
  if (!calls.length) return null
  return (
    <table className="calls">
      <thead>
        <tr><th>Job</th><th>Model</th><th>Source</th><th>Time</th></tr>
      </thead>
      <tbody>
        {calls.map((c, i) => (
          <tr key={i}>
            <td>{c.role}</td>
            <td className="mono">{c.model}</td>
            <td><CallBadge call={c} showModel={false} /></td>
            <td className="muted">{c.latency_s > 0 ? `${c.latency_s.toFixed(1)} s` : '—'}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}
