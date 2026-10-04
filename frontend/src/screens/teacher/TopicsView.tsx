import { useCallback, useEffect, useState } from 'react'
import { BookPlus, Eye, EyeOff, LoaderCircle, Pencil, Trash2 } from 'lucide-react'
import { api } from '../../api'
import type { TeacherTopic } from '../../types'
import { TopicEditor } from './TopicEditor'

export function TopicsView({ onAuthError }: { onAuthError: (err: unknown) => void }) {
  const [topics, setTopics] = useState<TeacherTopic[] | null>(null)
  const [editing, setEditing] = useState<TeacherTopic | 'new' | null>(null)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(() => {
    api.teacher.topics().then((data) => setTopics(data.topics)).catch((err) => {
      onAuthError(err)
      setError((err as Error).message)
    })
  }, [onAuthError])

  useEffect(load, [load])

  const togglePublished = async (topic: TeacherTopic) => {
    try {
      await api.teacher.updateTopic(topic.id, { ...topic, published: !topic.published })
      load()
    } catch (err) {
      setError((err as Error).message)
    }
  }

  const remove = async (topic: TeacherTopic) => {
    if (!window.confirm(`Delete "${topic.title}"? Students will lose access to its lessons.`)) return
    try {
      await api.teacher.deleteTopic(topic.id)
      load()
    } catch (err) {
      setError((err as Error).message)
    }
  }

  if (editing) {
    return (
      <TopicEditor
        topic={editing === 'new' ? null : editing}
        onCancel={() => setEditing(null)}
        onSaved={() => {
          setEditing(null)
          load()
        }}
      />
    )
  }

  return (
    <div className="teacher-page">
      <header className="page-header row">
        <div>
          <p className="eyebrow">Curriculum</p>
          <h1>Topics</h1>
          <p className="lead">Each topic is taught one-to-one, adapted to every student's model.</p>
        </div>
        <button type="button" className="primary-button" onClick={() => setEditing('new')}><BookPlus size={16} /> New topic</button>
      </header>
      {error && <p className="form-error">{error}</p>}
      {!topics && !error && <p className="muted"><LoaderCircle className="spin" size={16} /> Loading topics…</p>}
      <div className="topic-grid">
        {topics?.map((topic) => (
          <article className="panel topic-card" key={topic.id}>
            <div className="topic-card-head">
              <span className={`status-pill ${topic.published ? 'live' : ''}`}>{topic.published ? 'Published' : 'Draft'}</span>
              <span className="muted small">{topic.subject} · Grade {topic.gradeLevel}</span>
            </div>
            <h3>{topic.title}</h3>
            <p className="topic-desc">{topic.description || 'No description.'}</p>
            <ol className="topic-lessons">
              {topic.lessons.map((lesson) => <li key={lesson.id}>{lesson.title}</li>)}
            </ol>
            <p className="muted small">By {topic.createdByName}</p>
            <div className="topic-actions">
              {topic.canEdit && <button type="button" className="ghost-button small" onClick={() => setEditing(topic)}><Pencil size={14} /> Edit</button>}
              {topic.canEdit && (
                <button type="button" className="ghost-button small" onClick={() => togglePublished(topic)}>
                  {topic.published ? <><EyeOff size={14} /> Unpublish</> : <><Eye size={14} /> Publish</>}
                </button>
              )}
              {topic.canDelete && <button type="button" className="ghost-button small danger" onClick={() => remove(topic)}><Trash2 size={14} /> Delete</button>}
            </div>
          </article>
        ))}
      </div>
    </div>
  )
}
