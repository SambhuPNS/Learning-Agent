import { useEffect, useState } from 'react'
import { ArrowLeft, LoaderCircle } from 'lucide-react'
import { api } from '../../api'
import type { HomeworkResults } from '../../types'

const STATUS_LABEL = { not_started: 'Not started', in_progress: 'In progress', overdue: 'Overdue', submitted: 'Handed in', late: 'Handed in late' } as const
const formatDate = (iso: string | null) => (iso ? new Date(iso).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' }) : '')
const tone = (percent: number) => (percent >= 75 ? 'high' : percent >= 45 ? 'mid' : 'low')

export function HomeworkResultsView({ homeworkId, onBack, onAuthError }: { homeworkId: string; onBack: () => void; onAuthError: (err: unknown) => void }) {
  const [data, setData] = useState<HomeworkResults | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api.teacher.homeworkResults(homeworkId).then(setData).catch((err) => {
      onAuthError(err)
      setError((err as Error).message)
    })
  }, [homeworkId, onAuthError])

  if (error) return <div className="teacher-page"><button type="button" className="ghost-button" onClick={onBack}><ArrowLeft size={15} /> All homework</button><p className="form-error">{error}</p></div>
  if (!data) return <p className="muted"><LoaderCircle className="spin" size={16} /> Loading results…</p>

  const handedIn = data.students.filter((s) => s.status === 'submitted' || s.status === 'late').length

  return (
    <div className="teacher-page">
      <button type="button" className="ghost-button" onClick={onBack}><ArrowLeft size={15} /> All homework</button>
      <header className="page-header">
        <p className="eyebrow">{data.homework.topicTitle} · {data.homework.lessonTitle}</p>
        <h1>{data.homework.title}</h1>
        <p className="lead">Due {formatDate(data.homework.dueAt)}. {handedIn} of {data.students.length} students have handed in
          {data.averagePercent !== null && <>, with an average of <strong>{data.averagePercent}%</strong></>}.</p>
      </header>

      <div className="editor-columns hw-result-columns">
        <section className="panel">
          <h3>Questions</h3>
          {data.questions.every((q) => q.percentCorrect === null) && <p className="muted small">Question statistics appear once students hand in.</p>}
          <ol className="hw-question-stats">
            {data.questions.map((q) => (
              <li key={q.questionId}>
                <span>{q.prompt}</span>
                {q.percentCorrect !== null && (
                  <span className="cell-mastery">
                    <span className={`mastery-bar ${tone(q.percentCorrect)}`}><i style={{ width: `${q.percentCorrect}%` }} /></span>
                    <strong>{q.percentCorrect}%</strong>
                  </span>
                )}
              </li>
            ))}
          </ol>
        </section>
        <section className="panel">
          <h3>Common mistakes</h3>
          {data.misconceptions.length
            ? <ul className="hw-mistakes">{data.misconceptions.map((m) => <li key={m.label}><span>{m.label}</span><strong>{m.count}</strong></li>)}</ul>
            : <p className="muted small">No mistakes to show yet.</p>}
        </section>
      </div>

      <section className="panel table-wrap">
        <table className="student-table">
          <thead><tr><th>Student</th><th>Status</th><th>Score</th><th>Handed in</th></tr></thead>
          <tbody>
            {data.students.map((s) => (
              <tr key={s.userId}>
                <td><strong>{s.name}</strong><br /><span className="muted small">{s.email}</span></td>
                <td><span className={`hw-chip ${s.status === 'overdue' || s.status === 'late' ? 'late' : s.status === 'submitted' ? 'done' : ''}`}>{STATUS_LABEL[s.status]}</span></td>
                <td>{s.score !== null ? `${s.score}/${s.total}` : '—'}</td>
                <td className="muted small">{formatDate(s.submittedAt)}</td>
              </tr>
            ))}
            {!data.students.length && <tr><td colSpan={4} className="muted">No students have signed up yet.</td></tr>}
          </tbody>
        </table>
      </section>
    </div>
  )
}
