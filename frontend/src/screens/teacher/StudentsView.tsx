import { useEffect, useState } from 'react'
import { ArrowLeft, CheckCircle2, CircleHelp, Flag, Lightbulb, LoaderCircle, MessageCircleQuestion, Play, RefreshCw, XCircle } from 'lucide-react'
import { api } from '../../api'
import { BehaviourStats, ConceptList, MasteryBar, StrategyChart } from '../../components/Insights'
import { STRATEGY_LABEL } from '../../labels'
import type { LearningEvent, StudentDetail, StudentRow } from '../../types'

const timeAgo = (iso: string | null) => {
  if (!iso) return 'never'
  const minutes = Math.round((Date.now() - new Date(iso).getTime()) / 60000)
  if (minutes < 1) return 'just now'
  if (minutes < 60) return `${minutes} min ago`
  const hours = Math.round(minutes / 60)
  return hours < 24 ? `${hours} h ago` : `${Math.round(hours / 24)} d ago`
}
const seconds = (ms: unknown) => (typeof ms === 'number' ? `${(ms / 1000).toFixed(1)}s` : '')

function describe(event: LearningEvent): { icon: React.ReactNode; text: string; tone?: string } | null {
  switch (event.type) {
    case 'answer':
      return {
        icon: event.correct ? <CheckCircle2 size={15} /> : <XCircle size={15} />,
        tone: event.correct ? 'good' : 'bad',
        text: `Answered "${event.answer}" to "${event.question}" in ${seconds(event.responseMs)}${event.slow ? ' (slow)' : ''}`
          + ` via ${event.inputMode ?? 'typing'}${event.usedHint ? ', after a hint' : ''}`
          + (event.misconception ? ` · misconception: ${event.misconception}` : ''),
      }
    case 'hint':
      return { icon: <Lightbulb size={15} />, tone: 'warn', text: `Asked for a hint after ${seconds(event.waitedMs)}` }
    case 'explain_again':
      return { icon: <RefreshCw size={15} />, tone: 'warn', text: `Asked to explain again${event.strategy ? ` (the ${STRATEGY_LABEL[event.strategy as keyof typeof STRATEGY_LABEL]?.toLowerCase()} explanation didn't land)` : ''}` }
    case 'question_asked':
      return { icon: <MessageCircleQuestion size={15} />, text: `Asked: "${event.text}"` }
    case 'tutor_step':
      if (event.kind !== 'teach' || !event.strategy) return null
      return { icon: <CircleHelp size={15} />, text: `Tutor taught "${event.title}" using ${STRATEGY_LABEL[event.strategy as keyof typeof STRATEGY_LABEL]?.toLowerCase()}` }
    case 'lesson_started':
      return { icon: <Play size={15} />, text: 'Started the lesson' }
    case 'lesson_completed':
      return { icon: <Flag size={15} />, tone: 'good', text: `Completed the lesson (${event.mastery}% mastery)` }
    default:
      return null
  }
}

function StudentDetailView({ id, onBack, onAuthError }: { id: string; onBack: () => void; onAuthError: (err: unknown) => void }) {
  const [detail, setDetail] = useState<StudentDetail | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api.teacher.student(id).then(setDetail).catch((err) => {
      onAuthError(err)
      setError((err as Error).message)
    })
  }, [id, onAuthError])

  if (error) return <p className="form-error">{error}</p>
  if (!detail) return <p className="muted"><LoaderCircle className="spin" size={16} /> Loading student model…</p>
  const { student, insights, events } = detail
  const profile = student.profile
  const timeline = events.map((event) => ({ event, info: describe(event) })).filter((row) => row.info)

  return (
    <div className="teacher-page">
      <button type="button" className="ghost-button" onClick={onBack}><ArrowLeft size={15} /> All students</button>
      <header className="page-header">
        <p className="eyebrow">Student model</p>
        <h1>{student.name}</h1>
        <p className="lead">
          {student.email}
          {profile && <> · Grade {profile.grade} · chose "{STRATEGY_LABEL[profile.learningStyle]}" · pace {profile.pace} · interests: {profile.interests.join(', ') || '—'}</>}
        </p>
      </header>

      {insights.recommendations.length > 0 && (
        <section className="panel recommend-panel">
          <h3>What the model has learned</h3>
          <ul>{insights.recommendations.map((text) => <li key={text}>{text}</li>)}</ul>
        </section>
      )}

      <div className="two-col">
        <section className="panel">
          <h3>Which explanations work</h3>
          <StrategyChart insights={insights} />
        </section>
        <section className="panel">
          <h3>Behaviour</h3>
          <BehaviourStats insights={insights} />
          {insights.misconceptions.length > 0 && (
            <>
              <h4>Misconceptions seen</h4>
              <ol className="misconception-list">
                {insights.misconceptions.map((item) => <li key={item.label}><span>{item.label}</span><b>{item.count}×</b></li>)}
              </ol>
            </>
          )}
        </section>
      </div>

      <div className="two-col">
        <section className="panel">
          <h3>Mastery by lesson</h3>
          <ConceptList insights={insights} empty="This student hasn't answered any questions yet." />
        </section>
        <section className="panel">
          <h3>Recent activity</h3>
          {!timeline.length && <p className="muted small">No activity yet.</p>}
          <ul className="timeline">
            {timeline.slice(0, 25).map(({ event, info }) => (
              <li key={event.id} className={info!.tone}>
                {info!.icon}
                <div><span>{info!.text}</span><small>{event.lessonTitle} · {timeAgo(event.ts)}</small></div>
              </li>
            ))}
          </ul>
        </section>
      </div>
    </div>
  )
}

export function StudentsView({ onAuthError }: { onAuthError: (err: unknown) => void }) {
  const [rows, setRows] = useState<StudentRow[] | null>(null)
  const [selected, setSelected] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (selected) return
    api.teacher.students().then((data) => setRows(data.students)).catch((err) => {
      onAuthError(err)
      setError((err as Error).message)
    })
  }, [selected, onAuthError])

  if (selected) return <StudentDetailView id={selected} onBack={() => setSelected(null)} onAuthError={onAuthError} />

  return (
    <div className="teacher-page">
      <header className="page-header">
        <p className="eyebrow">Students</p>
        <h1>Every learner's model</h1>
        <p className="lead">Built from how each student actually answers: speed, mistakes, hints, and which explanations help.</p>
      </header>
      {error && <p className="form-error">{error}</p>}
      {!rows && !error && <p className="muted"><LoaderCircle className="spin" size={16} /> Loading students…</p>}
      {rows && !rows.length && <p className="muted">No students have signed up yet.</p>}
      {rows && rows.length > 0 && (
        <div className="panel table-wrap">
          <table className="student-table">
            <thead>
              <tr><th>Student</th><th>Mastery</th><th>Lessons</th><th>Learns best with</th><th>Avg answer</th><th>Watch for</th><th>Last active</th></tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.id} onClick={() => setSelected(row.id)} tabIndex={0} onKeyDown={(e) => e.key === 'Enter' && setSelected(row.id)}>
                  <td><strong>{row.name}</strong><small>{row.onboarded ? `Grade ${row.grade}` : 'Not onboarded'}</small></td>
                  <td>
                    {row.overallMastery !== null ? <div className="cell-mastery"><MasteryBar value={row.overallMastery} /><b>{row.overallMastery}%</b></div> : '—'}
                    {row.needsSupport && <span className="status-pill warn">needs support</span>}
                  </td>
                  <td>{row.lessonsCompleted}/{row.lessonsStarted} done</td>
                  <td>{row.bestStrategy ? STRATEGY_LABEL[row.bestStrategy] : '—'}{row.bestStrategy && row.selfReportedStrategy && row.bestStrategy !== row.selfReportedStrategy && <small>chose {STRATEGY_LABEL[row.selfReportedStrategy]}</small>}</td>
                  <td>{row.avgResponseSec !== null ? `${row.avgResponseSec}s` : '—'}</td>
                  <td className="clip">{row.topMisconception ?? '—'}</td>
                  <td>{timeAgo(row.lastActive)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
