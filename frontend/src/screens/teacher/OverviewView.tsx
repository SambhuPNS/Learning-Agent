import { useEffect, useState } from 'react'
import { AlertTriangle, BookCheck, Brain, LoaderCircle, Users } from 'lucide-react'
import { api } from '../../api'
import { MasteryBar } from '../../components/Insights'
import type { ClassOverview } from '../../types'

export function OverviewView({ onAuthError }: { onAuthError: (err: unknown) => void }) {
  const [data, setData] = useState<ClassOverview | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api.teacher.overview().then(setData).catch((err) => {
      onAuthError(err)
      setError((err as Error).message)
    })
  }, [onAuthError])

  if (error) return <p className="form-error">{error}</p>
  if (!data) return <p className="muted"><LoaderCircle className="spin" size={16} /> Loading class insights…</p>

  const rated = data.strategies.filter((s) => s.successRate !== null)
  return (
    <div className="teacher-page">
      <header className="page-header">
        <p className="eyebrow">Class overview</p>
        <h1>How your students are learning</h1>
      </header>

      <section className="stat-grid">
        <div className="stat"><Users size={18} /><strong>{data.studentCount}</strong><span>students ({data.activeStudents} active)</span></div>
        <div className="stat"><Brain size={18} /><strong>{data.averageMastery ?? '—'}{data.averageMastery !== null ? '%' : ''}</strong><span>average mastery</span></div>
        <div className="stat"><BookCheck size={18} /><strong>{data.lessonsCompleted}</strong><span>lessons completed</span></div>
        <div className={`stat ${data.needSupport ? 'warn' : ''}`}><AlertTriangle size={18} /><strong>{data.needSupport}</strong><span>need support</span></div>
      </section>

      <div className="two-col">
        <section className="panel">
          <h3>Concept mastery (class average)</h3>
          {!data.concepts.length && <p className="muted small">No answers yet. Mastery appears once students start practising.</p>}
          <ul className="concept-list">
            {data.concepts.map((concept) => (
              <li key={concept.lessonId}>
                <div><strong>{concept.lessonTitle}</strong><span>{concept.topicTitle} · {concept.students} student{concept.students === 1 ? '' : 's'}</span></div>
                <MasteryBar value={concept.mastery} />
                <b>{concept.mastery}%</b>
              </li>
            ))}
          </ul>
        </section>
        <section className="panel">
          <h3>Common misconceptions</h3>
          {!data.misconceptions.length && <p className="muted small">None detected yet. Gemini tags the misconception behind each wrong answer.</p>}
          <ol className="misconception-list">
            {data.misconceptions.map((item) => (
              <li key={item.label}><span>{item.label}</span><b>{item.count}×</b></li>
            ))}
          </ol>
        </section>
      </div>

      <section className="panel">
        <h3>Strategy effectiveness (class)</h3>
        <p className="muted small">Share of answers that were correct right after each kind of explanation.</p>
        {!rated.length && <p className="muted small">Not enough evidence yet.</p>}
        <div className="strategy-chart">
          {data.strategies.map((item) => (
            <div className="strategy-row" key={item.strategy}>
              <span className="strategy-name">{item.label}</span>
              <div className="strategy-track"><i className={`s-${item.strategy}`} style={{ width: `${item.successRate ?? 0}%` }} /></div>
              <span className="strategy-value">{item.successRate !== null ? `${item.successRate}%` : '—'}<small>{item.attempts} obs</small></span>
            </div>
          ))}
        </div>
      </section>
    </div>
  )
}
