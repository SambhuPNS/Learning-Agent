import { useEffect, useState } from 'react'
import { LoaderCircle } from 'lucide-react'
import { api } from '../../api'
import { USAGE_FEATURE_LABEL } from '../../labels'
import type { UsageCall, UsageGroup, UsageReport } from '../../types'

const DAY_CHOICES = [1, 7, 30]
const number = (value: number) => value.toLocaleString()
const seconds = (ms: number | null) => (ms === null ? '–' : `${(ms / 1000).toFixed(1)}s`)
const when = (iso: string) => new Date(iso).toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit' })
const OUTCOME_LABEL: Record<UsageCall['outcome'], string> = { ok: 'OK', blocked: 'Blocked by safety', error: 'Failed', cancelled: 'Cancelled' }

function GroupTable({ title, rows, label }: { title: string; rows: UsageGroup[]; label: (name: string) => string }) {
  const max = Math.max(1, ...rows.map((row) => row.totalTokens))
  return (
    <section className="panel table-wrap">
      <h3 className="usage-title">{title}</h3>
      <table className="student-table">
        <thead><tr><th>Name</th><th>Calls</th><th>Input</th><th>Output</th><th>Total tokens</th><th>Avg time</th></tr></thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.name}>
              <td><strong>{label(row.name)}</strong></td>
              <td>{number(row.calls)}</td>
              <td>{number(row.inputTokens)}</td>
              <td>{number(row.outputTokens + row.thinkingTokens)}</td>
              <td><div className="usage-bar"><span className="mastery-bar mid"><i style={{ width: `${(100 * row.totalTokens) / max}%` }} /></span><strong>{number(row.totalTokens)}</strong></div></td>
              <td className="usage-dim">{seconds(row.avgLatencyMs)}</td>
            </tr>
          ))}
          {!rows.length && <tr><td colSpan={6} className="usage-dim">No calls in this period.</td></tr>}
        </tbody>
      </table>
    </section>
  )
}

export function UsageView({ onAuthError }: { onAuthError: (err: unknown) => void }) {
  const [days, setDays] = useState(7)
  const [report, setReport] = useState<UsageReport | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let current = true
    api.teacher.usage(days).then((data) => current && setReport(data)).catch((err) => {
      onAuthError(err)
      if (current) setError((err as Error).message)
    })
    return () => { current = false }
  }, [days, onAuthError])

  const choose = (choice: number) => {
    setDays(choice)
    setReport(null)
    setError(null)
  }

  const peak = Math.max(1, ...(report?.byDay.map((day) => day.totalTokens) ?? [1]))

  return (
    <div className="teacher-page">
      <header className="page-header row">
        <div>
          <p className="eyebrow">Traceability</p>
          <h1>AI usage</h1>
          <p className="lead">Every Gemini call, with its tokens, the student and feature it served, and a trace ID you can follow in Cloud Logging.</p>
        </div>
        <div className="usage-days" role="group" aria-label="Period">
          {DAY_CHOICES.map((choice) => (
            <button key={choice} type="button" className={days === choice ? 'active' : ''} onClick={() => choose(choice)}>
              {choice === 1 ? 'Today' : `${choice} days`}
            </button>
          ))}
        </div>
      </header>

      {error && <p className="form-error">{error}</p>}
      {!report && !error && <p className="muted"><LoaderCircle className="spin" size={16} /> Loading usage…</p>}

      {report && (
        <>
          <div className="stat-grid usage-stats">
            <div className="stat"><strong>{number(report.totals.calls)}</strong><span>Gemini calls</span></div>
            <div className="stat"><strong>{number(report.totals.totalTokens)}</strong><span>total tokens</span></div>
            <div className="stat"><strong>{number(report.totals.inputTokens)}</strong><span>input tokens</span></div>
            <div className="stat"><strong>{number(report.totals.outputTokens + report.totals.thinkingTokens)}</strong><span>output + thinking tokens</span></div>
            <div className="stat"><strong>{seconds(report.totals.avgLatencyMs)}</strong><span>average response time</span></div>
            <div className="stat"><strong>{report.totals.errors + report.totals.blocked}</strong><span>failed or blocked ({report.totals.cancelled} cancelled)</span></div>
          </div>
          {report.truncated && <p className="dock-alert">Showing the most recent {number(report.totals.calls)} calls in this period.</p>}

          <section className="panel">
            <h3 className="usage-title">Tokens per day</h3>
            <div className="usage-chart" role="img" aria-label="Total tokens per day">
              {report.byDay.map((day) => (
                <div key={day.date} className="usage-col" title={`${day.date}: ${number(day.totalTokens)} tokens, ${day.calls} calls`}>
                  <i style={{ height: `${Math.max(day.totalTokens ? 4 : 0, (100 * day.totalTokens) / peak)}%` }} />
                  <span>{report.byDay.length <= 7 ? day.date.slice(5) : day.date.slice(8)}</span>
                </div>
              ))}
            </div>
          </section>

          <GroupTable title="By feature" rows={report.byFeature} label={(name) => USAGE_FEATURE_LABEL[name] ?? name} />
          <GroupTable title="By model" rows={report.byModel} label={(name) => name} />

          <section className="panel table-wrap">
            <h3 className="usage-title">Most active students</h3>
            <table className="student-table">
              <thead><tr><th>Student</th><th>Calls</th><th>Total tokens</th></tr></thead>
              <tbody>
                {report.byStudent.map((student) => (
                  <tr key={student.userId}><td><strong>{student.name}</strong></td><td>{number(student.calls)}</td><td>{number(student.totalTokens)}</td></tr>
                ))}
                {!report.byStudent.length && <tr><td colSpan={3} className="usage-dim">No student calls in this period.</td></tr>}
              </tbody>
            </table>
          </section>

          <section className="panel table-wrap">
            <h3 className="usage-title">Recent calls</h3>
            <table className="student-table">
              <thead><tr><th>Time</th><th>Feature</th><th>Student</th><th>Model</th><th>Tokens (in / out)</th><th>Time taken</th><th>Result</th><th>Trace ID</th></tr></thead>
              <tbody>
                {report.recent.map((call) => (
                  <tr key={call.id}>
                    <td className="usage-dim">{when(call.ts)}</td>
                    <td>{USAGE_FEATURE_LABEL[call.feature] ?? call.feature}{call.ref && <><br /><span className="usage-dim">{call.ref}</span></>}</td>
                    <td>{call.student ?? <span className="usage-dim">–</span>}</td>
                    <td className="usage-dim">{call.model}</td>
                    <td>{number(call.inputTokens)} / {number(call.outputTokens + call.thinkingTokens)}</td>
                    <td className="usage-dim">{seconds(call.latencyMs)}</td>
                    <td><span className={`hw-chip ${call.outcome === 'ok' ? 'done' : 'late'}`}>{OUTCOME_LABEL[call.outcome]}{call.httpStatus ? ` ${call.httpStatus}` : ''}</span></td>
                    <td className="usage-trace">{call.traceId ?? '–'}</td>
                  </tr>
                ))}
                {!report.recent.length && <tr><td colSpan={8} className="usage-dim">No calls yet. Open a lesson or draft a topic, and they appear here.</td></tr>}
              </tbody>
            </table>
          </section>
          <p className="muted small usage-note">Records hold metadata only: no prompts, answers or student text. They are kept for 30 days. In Cloud Logging, search <code>jsonPayload.message="gemini_usage"</code> and filter by trace ID.</p>
        </>
      )}
    </div>
  )
}
