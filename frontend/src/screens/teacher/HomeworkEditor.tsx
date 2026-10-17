import { useEffect, useMemo, useState } from 'react'
import { ArrowLeft, LoaderCircle, Plus, Sparkles, Trash2 } from 'lucide-react'
import { api } from '../../api'
import type { HomeworkQuestionEdit, TeacherTopic } from '../../types'

type EditableQuestion = {
  id?: string
  prompt: string
  format: 'choice' | 'text'
  optionsText: string
  correct: string
  acceptedText: string
  explanation: string
  misconception: string
}

const lines = (text: string) => text.split('\n').map((line) => line.trim()).filter(Boolean)
const pad = (value: number) => String(value).padStart(2, '0')
const toLocalInput = (date: Date) => `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`
const defaultDue = () => {
  const date = new Date()
  date.setDate(date.getDate() + 7)
  date.setHours(17, 0, 0, 0)
  return toLocalInput(date)
}

const toEditable = (q: HomeworkQuestionEdit): EditableQuestion => ({
  id: q.id,
  prompt: q.prompt,
  format: q.format,
  optionsText: q.options.join('\n'),
  correct: q.expectedAnswer,
  acceptedText: q.acceptableAnswers.join('\n'),
  explanation: q.explanation,
  misconception: q.misconception,
})

const toInput = (q: EditableQuestion): HomeworkQuestionEdit => {
  const accepted = lines(q.acceptedText)
  return {
    id: q.id,
    prompt: q.prompt.trim(),
    format: q.format,
    options: q.format === 'choice' ? lines(q.optionsText) : [],
    expectedAnswer: q.format === 'choice' ? q.correct : accepted[0] ?? '',
    acceptableAnswers: q.format === 'choice' ? [] : accepted,
    explanation: q.explanation.trim(),
    misconception: q.misconception.trim(),
  }
}

const blankQuestion = (): EditableQuestion => ({ prompt: '', format: 'choice', optionsText: '', correct: '', acceptedText: '', explanation: '', misconception: '' })

export function HomeworkEditor({ homeworkId, onCancel, onSaved, onAuthError }: {
  homeworkId: string | null
  onCancel: () => void
  onSaved: () => void
  onAuthError: (err: unknown) => void
}) {
  const [topics, setTopics] = useState<TeacherTopic[] | null>(null)
  const [loading, setLoading] = useState(Boolean(homeworkId))
  const [lessonId, setLessonId] = useState('')
  const [title, setTitle] = useState('')
  const [titleTouched, setTitleTouched] = useState(false)
  const [instructions, setInstructions] = useState('')
  const [dueAt, setDueAt] = useState(defaultDue)
  const [published, setPublished] = useState(true)
  const [questions, setQuestions] = useState<EditableQuestion[]>([])
  const [count, setCount] = useState(6)
  const [locked, setLocked] = useState(false)
  const [drafting, setDrafting] = useState(false)
  const [saving, setSaving] = useState(false)
  const [note, setNote] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const load = async () => {
      try {
        const [topicData, detail] = await Promise.all([api.teacher.topics(), homeworkId ? api.teacher.homeworkDetail(homeworkId) : null])
        setTopics(topicData.topics)
        if (detail) {
          setLessonId(detail.lessonId)
          setTitle(detail.title)
          setTitleTouched(true)
          setInstructions(detail.instructions)
          setDueAt(toLocalInput(new Date(detail.dueAt)))
          setPublished(detail.published)
          setQuestions(detail.questions.map(toEditable))
          setLocked(detail.locked)
        }
      } catch (err) {
        onAuthError(err)
        setError((err as Error).message)
      } finally {
        setLoading(false)
      }
    }
    void load()
  }, [homeworkId, onAuthError])

  const lessons = useMemo(() => topics?.flatMap((topic) => topic.lessons.map((lesson) => ({ id: lesson.id as string, label: `${topic.title} › ${lesson.title}`, title: lesson.title }))) ?? [], [topics])

  const chooseLesson = (id: string) => {
    setLessonId(id)
    const lesson = lessons.find((item) => item.id === id)
    if (lesson && !titleTouched) setTitle(`${lesson.title} practice`)
  }

  const update = (index: number, patch: Partial<EditableQuestion>) =>
    setQuestions((current) => current.map((q, i) => (i === index ? { ...q, ...patch } : q)))

  const generate = async () => {
    if (questions.length && !window.confirm('Replace the current questions with new ones?')) return
    setDrafting(true)
    setError(null)
    setNote(null)
    try {
      const result = await api.teacher.draftHomework(lessonId, count)
      setQuestions(result.questions.map(toEditable))
      setNote(result.source === 'gemini'
        ? `Gemini wrote ${result.questions.length} questions. Check every answer before you publish.`
        : 'Gemini is unavailable, so simple true/false questions were made from the lesson. Please review and edit them.')
    } catch (err) {
      onAuthError(err)
      setError((err as Error).message)
    } finally {
      setDrafting(false)
    }
  }

  const save = async () => {
    setError(null)
    if (!lessonId) return setError('Choose the lesson this homework is about.')
    if (!title.trim()) return setError('Give the homework a title.')
    if (!dueAt || Number.isNaN(new Date(dueAt).getTime())) return setError('Choose a due date.')
    if (!questions.length) return setError('Add at least one question.')
    const input = { title: title.trim(), instructions: instructions.trim(), lessonId, dueAt: new Date(dueAt).toISOString(), published, questions: questions.map(toInput) }
    setSaving(true)
    try {
      if (homeworkId) await api.teacher.updateHomework(homeworkId, input)
      else await api.teacher.createHomework(input)
      onSaved()
    } catch (err) {
      onAuthError(err)
      setError((err as Error).message)
      setSaving(false)
    }
  }

  if (loading) return <p className="muted"><LoaderCircle className="spin" size={16} /> Loading…</p>

  return (
    <div className="teacher-page">
      <button type="button" className="ghost-button" onClick={onCancel}><ArrowLeft size={15} /> All homework</button>
      <header className="page-header">
        <p className="eyebrow">{homeworkId ? 'Edit homework' : 'New homework'}</p>
        <h1>{homeworkId ? title || 'Homework' : 'Set some practice'}</h1>
        <p className="lead">Pick a lesson, let Gemini draft the questions, then check every answer. Students are marked automatically against the answers you set here.</p>
      </header>

      {locked && <p className="dock-alert">Students have already started this homework, so the lesson and questions are locked. You can still change the title, instructions, due date and visibility.</p>}

      <section className="panel form-grid">
        <label className="span-3">Lesson
          <select value={lessonId} onChange={(e) => chooseLesson(e.target.value)} disabled={locked}>
            <option value="">Choose a lesson…</option>
            {lessons.map((lesson) => <option key={lesson.id} value={lesson.id}>{lesson.label}</option>)}
          </select>
        </label>
        <label>Title<input value={title} maxLength={80} onChange={(e) => { setTitle(e.target.value); setTitleTouched(true) }} placeholder="Comparing fractions practice" /></label>
        <label className="span-2">Due
          <input type="datetime-local" value={dueAt} onChange={(e) => setDueAt(e.target.value)} />
        </label>
        <label className="span-3">Instructions for students <small className="muted">(optional)</small>
          <textarea rows={2} maxLength={500} value={instructions} onChange={(e) => setInstructions(e.target.value)} placeholder="Take your time. There is one attempt and no hints." />
        </label>
        <div className="span-3 hw-generate">
          <label>Questions
            <select value={count} onChange={(e) => setCount(Number(e.target.value))} disabled={locked}>
              {[4, 5, 6, 8, 10].map((n) => <option key={n} value={n}>{n} questions</option>)}
            </select>
          </label>
          <button type="button" className="primary-button" onClick={() => void generate()} disabled={!lessonId || drafting || locked}>
            {drafting ? <LoaderCircle className="spin" size={16} /> : <Sparkles size={16} />} {questions.length ? 'Regenerate questions' : 'Generate questions with Gemini'}
          </button>
        </div>
        {note && <p className="dock-alert span-3">{note}</p>}
      </section>

      <div className="section-head">
        <h2 className="section-title">Questions ({questions.length})</h2>
        <button type="button" className="ghost-button" disabled={locked || questions.length >= 10} onClick={() => setQuestions([...questions, blankQuestion()])}><Plus size={15} /> Add question</button>
      </div>
      {!questions.length && <p className="muted small">Generate questions from the lesson, or add them by hand.</p>}

      <fieldset className="hw-fieldset" disabled={locked}>
        <div className="lesson-editor-list">
          {questions.map((q, index) => {
            const options = lines(q.optionsText)
            return (
              <article className="panel lesson-editor" key={q.id ?? `new-${index}`}>
                <header>
                  <span className="lesson-index">{index + 1}</span>
                  <input className="title-input" value={q.prompt} maxLength={300} placeholder="Question" onChange={(e) => update(index, { prompt: e.target.value })} />
                  <select className="hw-format" value={q.format} onChange={(e) => update(index, { format: e.target.value as 'choice' | 'text' })} aria-label="Question type">
                    <option value="choice">Multiple choice</option>
                    <option value="text">Typed answer</option>
                  </select>
                  <button type="button" className="icon-ghost" aria-label="Remove question" onClick={() => setQuestions(questions.filter((_, i) => i !== index))}><Trash2 size={16} /></button>
                </header>
                <div className="editor-columns">
                  {q.format === 'choice' ? (
                    <>
                      <label>Answer choices <small>one per line, up to 4</small>
                        <textarea rows={4} value={q.optionsText} onChange={(e) => update(index, { optionsText: e.target.value })} />
                      </label>
                      <label>Correct answer
                        <select value={options.includes(q.correct) ? q.correct : ''} onChange={(e) => update(index, { correct: e.target.value })}>
                          <option value="">Choose…</option>
                          {options.map((option) => <option key={option} value={option}>{option}</option>)}
                        </select>
                      </label>
                    </>
                  ) : (
                    <label className="hw-wide">Accepted answers <small>one per line; the first is shown to students after they hand in</small>
                      <textarea rows={3} value={q.acceptedText} onChange={(e) => update(index, { acceptedText: e.target.value })} placeholder={'3/4\nthree quarters'} />
                    </label>
                  )}
                  <label>Explanation <small>shown after handing in</small>
                    <textarea rows={q.format === 'choice' ? 4 : 3} maxLength={400} value={q.explanation} onChange={(e) => update(index, { explanation: e.target.value })} />
                  </label>
                </div>
                <label>Mistake this question catches <small>optional; wrong answers are recorded against it</small>
                  <input value={q.misconception} maxLength={140} onChange={(e) => update(index, { misconception: e.target.value })} />
                </label>
              </article>
            )
          })}
        </div>
      </fieldset>

      {error && <p className="form-error">{error}</p>}
      <div className="editor-actions">
        <label className="switch-row inline">
          <input type="checkbox" checked={published} onChange={(e) => setPublished(e.target.checked)} />
          <span>Visible to students</span>
        </label>
        <button type="button" className="ghost-button" onClick={onCancel}>Cancel</button>
        <button type="button" className="primary-button" onClick={() => void save()} disabled={saving}>
          {saving && <LoaderCircle className="spin" size={16} />} Save homework
        </button>
      </div>
    </div>
  )
}
