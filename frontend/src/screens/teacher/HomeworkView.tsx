import { useCallback, useEffect, useState } from 'react'
import { BarChart3, ClipboardPlus, Eye, EyeOff, LoaderCircle, Pencil, Trash2 } from 'lucide-react'
import { api } from '../../api'
import { formatDue } from '../../labels'
import type { TeacherHomeworkRow } from '../../types'
import { HomeworkEditor } from './HomeworkEditor'
import { HomeworkResultsView } from './HomeworkResultsView'

export function HomeworkView({ onAuthError }: { onAuthError: (err: unknown) => void }) {
  const [rows, setRows] = useState<TeacherHomeworkRow[] | null>(null)
  const [editing, setEditing] = useState<string | 'new' | null>(null)
  const [viewing, setViewing] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(() => {
    api.teacher.homework().then((data) => setRows(data.homework)).catch((err) => {
      onAuthError(err)
      setError((err as Error).message)
    })
  }, [onAuthError])

  useEffect(load, [load])

  const togglePublished = async (row: TeacherHomeworkRow) => {
    setError(null)
    try {
      const { id: _id, locked: _locked, topicTitle: _topic, lessonTitle: _lesson, ...detail } = await api.teacher.homeworkDetail(row.id)
      await api.teacher.updateHomework(row.id, { ...detail, published: !row.published })
      load()
    } catch (err) {
      setError((err as Error).message)
    }
  }

  const remove = async (row: TeacherHomeworkRow) => {
    if (!window.confirm(`Delete "${row.title}"?`)) return
    setError(null)
    try {
      await api.teacher.deleteHomework(row.id)
      load()
    } catch (err) {
      setError((err as Error).message)
    }
  }

  if (editing) {
    return (
      <HomeworkEditor
        homeworkId={editing === 'new' ? null : editing}
        onAuthError={onAuthError}
        onCancel={() => setEditing(null)}
        onSaved={() => {
          setEditing(null)
          load()
        }}
      />
    )
  }
  if (viewing) return <HomeworkResultsView homeworkId={viewing} onAuthError={onAuthError} onBack={() => setViewing(null)} />

  return (
    <div className="teacher-page">
      <header className="page-header row">
        <div>
          <p className="eyebrow">Practice</p>
          <h1>Homework</h1>
          <p className="lead">Set auto-marked questions from any lesson. Every student's answers update their learning model.</p>
        </div>
        <button type="button" className="primary-button" onClick={() => setEditing('new')}><ClipboardPlus size={16} /> New homework</button>
      </header>
      {error && <p className="form-error">{error}</p>}
      {!rows && !error && <p className="muted"><LoaderCircle className="spin" size={16} /> Loading homework…</p>}
      {rows && !rows.length && <p className="panel muted">No homework yet. Choose <strong>New homework</strong> to set your first questions.</p>}
      <div className="topic-grid">
        {rows?.map((row) => (
          <article className="panel topic-card" key={row.id}>
            <div className="topic-card-head">
              <span className={`status-pill ${row.published ? 'live' : ''}`}>{row.published ? 'Visible to students' : 'Hidden'}</span>
              <span className="muted small">{row.questionCount} questions</span>
            </div>
            <h3>{row.title}</h3>
            <p className="topic-desc">{row.topicTitle} · {row.lessonTitle}</p>
            <p className="muted small">Due {formatDue(row.dueAt)}</p>
            <p className="hw-progress"><strong>{row.submitted}</strong> of {row.students} handed in{row.averagePercent !== null && <> · average <strong>{row.averagePercent}%</strong></>}</p>
            <div className="topic-actions">
              <button type="button" className="ghost-button small" onClick={() => setViewing(row.id)}><BarChart3 size={14} /> Results</button>
              <button type="button" className="ghost-button small" onClick={() => setEditing(row.id)}><Pencil size={14} /> Edit</button>
              <button type="button" className="ghost-button small" onClick={() => void togglePublished(row)}>
                {row.published ? <><EyeOff size={14} /> Hide</> : <><Eye size={14} /> Show</>}
              </button>
              <button type="button" className="ghost-button small danger" onClick={() => void remove(row)}><Trash2 size={14} /> Delete</button>
            </div>
          </article>
        ))}
      </div>
    </div>
  )
}
