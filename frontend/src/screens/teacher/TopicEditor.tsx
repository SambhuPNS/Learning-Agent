import { useRef, useState, type DragEvent } from 'react'
import { AlignLeft, ArrowLeft, FileText, FileUp, Globe, Link2, LoaderCircle, Plus, Sparkles, Trash2, UploadCloud, X } from 'lucide-react'
import { api } from '../../api'
import type { TeacherTopic, TopicInput, TopicLesson, UploadedFile } from '../../types'

type EditableLesson = { id?: string; title: string; summary: string; objectives: string; keyIdeas: string; misconceptions: string }

const MAX_FILE_BYTES = 10 * 1024 * 1024
type Source = 'text' | 'file' | 'url'
const SOURCES = [
  { id: 'text', label: 'Type text', hint: 'Describe the topic', icon: AlignLeft },
  { id: 'file', label: 'Upload file', hint: 'PDF, TXT or MD', icon: FileUp },
  { id: 'url', label: 'Web page', hint: 'Import from a link', icon: Globe },
] as const
const toEditable = (lesson: TopicLesson): EditableLesson => ({
  id: lesson.id,
  title: lesson.title,
  summary: lesson.summary,
  objectives: lesson.objectives.join('\n'),
  keyIdeas: lesson.keyIdeas.join('\n'),
  misconceptions: lesson.misconceptions.join('\n'),
})
const formatSize = (bytes: number) => (bytes >= 1024 * 1024 ? `${(bytes / (1024 * 1024)).toFixed(1)} MB` : `${Math.max(1, Math.round(bytes / 1024))} KB`)
const lines = (text: string) => text.split('\n').map((line) => line.trim()).filter(Boolean)
const blankLesson = (): EditableLesson => ({ title: '', summary: '', objectives: '', keyIdeas: '', misconceptions: '' })

function readFile(file: File): Promise<UploadedFile> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onerror = () => reject(new Error('Could not read the file.'))
    if (file.type === 'application/pdf' || file.name.toLowerCase().endsWith('.pdf')) {
      reader.onload = () => resolve({ name: file.name, mimeType: 'application/pdf', data: String(reader.result).split(',')[1] ?? '' })
      reader.readAsDataURL(file)
    } else {
      reader.onload = () => resolve({ name: file.name, mimeType: file.name.endsWith('.md') ? 'text/markdown' : 'text/plain', text: String(reader.result) })
      reader.readAsText(file)
    }
  })
}

export function TopicEditor({ topic, onSaved, onCancel }: { topic: TeacherTopic | null; onSaved: () => void; onCancel: () => void }) {
  const [subject, setSubject] = useState(topic?.subject ?? '')
  const [title, setTitle] = useState(topic?.title ?? '')
  const [gradeLevel, setGradeLevel] = useState(topic?.gradeLevel ?? 7)
  const [description, setDescription] = useState(topic?.description ?? '')
  const [published, setPublished] = useState(topic?.published ?? true)
  const [lessons, setLessons] = useState<EditableLesson[]>(topic ? topic.lessons.map(toEditable) : [])
  const [source, setSource] = useState<Source>('text')
  const [file, setFile] = useState<UploadedFile | null>(null)
  const [fileSize, setFileSize] = useState(0)
  const [web, setWeb] = useState<{ file: UploadedFile; url: string; words: number } | null>(null)
  const [urlInput, setUrlInput] = useState('')
  const [fetching, setFetching] = useState(false)
  const [dragging, setDragging] = useState(false)
  const fileInput = useRef<HTMLInputElement>(null)
  const [drafting, setDrafting] = useState(false)
  const [saving, setSaving] = useState(false)
  const [draftNote, setDraftNote] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  // Only the material for the chosen option is used when generating.
  const material = source === 'file' ? file : source === 'url' ? web?.file ?? null : null
  const canDraft = subject.trim() && title.trim() && (source === 'text' ? description.trim() : material)

  const chooseSource = (next: Source) => {
    setSource(next)
    setError(null)
    setDraftNote(null)
  }

  const chooseFile = async (selected: File | undefined) => {
    setError(null)
    if (!selected) return
    if (selected.size > MAX_FILE_BYTES) {
      setError('Please upload a file under 10 MB.')
      return
    }
    try {
      setFile(await readFile(selected))
      setFileSize(selected.size)
    } catch (err) {
      setError((err as Error).message)
    }
  }

  const fetchUrl = async () => {
    const url = urlInput.trim()
    if (!url) return
    setError(null)
    setFetching(true)
    try {
      const notes = await api.teacher.fetchNotesUrl(/^https?:\/\//i.test(url) ? url : `https://${url}`)
      setWeb({ file: { name: notes.title, mimeType: 'text/plain', text: notes.text }, url: notes.url, words: notes.words })
      setUrlInput('')
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setFetching(false)
    }
  }

  const dropFile = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault()
    setDragging(false)
    void chooseFile(event.dataTransfer.files?.[0])
  }

  const clearFile = () => {
    setFile(null)
    if (fileInput.current) fileInput.current.value = ''
  }

  const draft = async () => {
    setDrafting(true)
    setError(null)
    setDraftNote(null)
    try {
      const result = await api.teacher.draftTopic({
        subject, title, gradeLevel, description: source === 'text' ? description : '', file: material ?? undefined,
      })
      setLessons(result.lessons.map(toEditable))
      if (!description.trim() && result.summary) setDescription(result.summary)
      setDraftNote(result.source === 'gemini'
        ? `Gemini drafted ${result.lessons.length} lessons. Review and edit them before publishing.`
        : 'Gemini is unavailable, so a simple outline was created from your material. Please edit it.')
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setDrafting(false)
    }
  }

  const updateLesson = (index: number, patch: Partial<EditableLesson>) =>
    setLessons((current) => current.map((lesson, i) => (i === index ? { ...lesson, ...patch } : lesson)))

  const save = async () => {
    setError(null)
    const payload: TopicInput = {
      subject: subject.trim(),
      title: title.trim(),
      gradeLevel,
      description: description.trim(),
      published,
      lessons: lessons.map((lesson) => ({
        id: lesson.id,
        title: lesson.title.trim(),
        summary: lesson.summary.trim(),
        objectives: lines(lesson.objectives),
        keyIdeas: lines(lesson.keyIdeas),
        misconceptions: lines(lesson.misconceptions),
      })),
    }
    if (!payload.lessons.length || payload.lessons.some((l) => !l.title || !l.keyIdeas.length)) {
      setError('Every lesson needs a title and at least one key idea.')
      return
    }
    setSaving(true)
    try {
      if (topic) await api.teacher.updateTopic(topic.id, payload)
      else await api.teacher.createTopic(payload)
      onSaved()
    } catch (err) {
      setError((err as Error).message)
      setSaving(false)
    }
  }

  return (
    <div className="teacher-page">
      <button type="button" className="ghost-button" onClick={onCancel}><ArrowLeft size={15} /> All topics</button>
      <header className="page-header">
        <p className="eyebrow">{topic ? 'Edit topic' : 'New topic'}</p>
        <h1>{topic ? topic.title : 'Teach something new'}</h1>
        <p className="lead">Describe the topic or upload your notes. Gemini turns them into lessons, and each student is then taught them in the way that works for them.</p>
      </header>

      <section className="panel form-grid">
        <label>Subject<input value={subject} onChange={(e) => setSubject(e.target.value)} maxLength={40} placeholder="Science" /></label>
        <label>Topic title<input value={title} onChange={(e) => setTitle(e.target.value)} maxLength={80} placeholder="Photosynthesis" /></label>
        <label>Grade
          <select value={gradeLevel} onChange={(e) => setGradeLevel(Number(e.target.value))}>
            {Array.from({ length: 12 }, (_, i) => i + 1).map((grade) => <option key={grade} value={grade}>Grade {grade}</option>)}
          </select>
        </label>
        <div className="span-3 upload-block">
          <span className="upload-title" id="source-label">Where should the lessons come from?</span>
          <div className="source-tabs" role="radiogroup" aria-labelledby="source-label">
            {SOURCES.map(({ id, label, hint, icon: Icon }) => (
              <button key={id} type="button" role="radio" aria-checked={source === id} className={source === id ? 'active' : ''} onClick={() => chooseSource(id)}>
                <Icon size={18} /><strong>{label}</strong><span>{hint}</span>
              </button>
            ))}
          </div>

          {source === 'text' && (
            <label className="source-field">Description for the tutor
              <textarea value={description} onChange={(e) => setDescription(e.target.value)} maxLength={4000} rows={5}
                placeholder="What should students learn? Include key facts, vocabulary, examples you like to use, and common mistakes." />
            </label>
          )}

          {source === 'file' && (
            <div
              className={`dropzone ${dragging ? 'dragging' : ''} ${file ? 'has-file' : ''}`}
              role="button"
              tabIndex={0}
              aria-label={file ? 'Replace the uploaded notes' : 'Choose a notes file to upload'}
              onClick={() => fileInput.current?.click()}
              onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); fileInput.current?.click() } }}
              onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
              onDragLeave={() => setDragging(false)}
              onDrop={dropFile}
            >
              <input ref={fileInput} type="file" hidden accept=".pdf,.txt,.md,application/pdf,text/plain,text/markdown"
                onChange={(e) => void chooseFile(e.target.files?.[0])} />
              {file ? (
                <>
                  <FileText size={28} className="dropzone-icon" />
                  <div className="dropzone-text">
                    <strong>{file.name}</strong>
                    <span>{formatSize(fileSize)} · attached. Click to replace it.</span>
                  </div>
                  <button type="button" className="dropzone-remove" onClick={(e) => { e.stopPropagation(); clearFile() }} aria-label="Remove file">
                    <X size={15} /> Remove
                  </button>
                </>
              ) : (
                <>
                  <UploadCloud size={30} className="dropzone-icon" />
                  <div className="dropzone-text">
                    <strong>Drag a file here, or <u>browse</u></strong>
                    <span>PDF, TXT or Markdown, up to 10 MB</span>
                  </div>
                </>
              )}
            </div>
          )}

          {source === 'url' && (
            <>
              <div className="url-row">
                <input type="url" value={urlInput} onChange={(e) => setUrlInput(e.target.value)} placeholder="https://en.wikipedia.org/wiki/Photosynthesis"
                  onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); void fetchUrl() } }} aria-label="Web page address" />
                <button type="button" className="ghost-button" onClick={() => void fetchUrl()} disabled={!urlInput.trim() || fetching}>
                  {fetching ? <LoaderCircle className="spin" size={15} /> : <Globe size={15} />} {fetching ? 'Reading…' : web ? 'Replace page' : 'Import text'}
                </button>
              </div>
              {web && (
                <div className="dropzone has-file static">
                  <Link2 size={28} className="dropzone-icon" />
                  <div className="dropzone-text">
                    <strong>{web.file.name}</strong>
                    <span>{new URL(web.url).hostname} · {web.words.toLocaleString()} words imported</span>
                  </div>
                  <button type="button" className="dropzone-remove" onClick={() => setWeb(null)} aria-label="Remove web page"><X size={15} /> Remove</button>
                </div>
              )}
            </>
          )}

          <div className="generate-row">
            <p className="muted small">
              {material ? 'Your material is read when you click Generate.' : 'Fill in the subject and title, then provide the material above.'}
            </p>
            <button type="button" className="primary-button" onClick={draft} disabled={!canDraft || drafting}>
              {drafting ? <LoaderCircle className="spin" size={16} /> : <Sparkles size={16} />}
              {drafting ? 'Generating…' : lessons.length ? 'Regenerate lessons' : 'Generate lessons with Gemini'}
            </button>
          </div>
        </div>
        {draftNote && <p className="dock-alert span-3">{draftNote}</p>}
      </section>

      <div className="section-head">
        <h2 className="section-title">Lessons ({lessons.length})</h2>
        <button type="button" className="ghost-button" onClick={() => setLessons([...lessons, blankLesson()])}><Plus size={15} /> Add lesson</button>
      </div>
      {!lessons.length && <p className="muted small">Generate lessons from your description, or add them by hand.</p>}
      <div className="lesson-editor-list">
        {lessons.map((lesson, index) => (
          <article className="panel lesson-editor" key={lesson.id ?? `new-${index}`}>
            <header>
              <span className="lesson-index">{index + 1}</span>
              <input className="title-input" value={lesson.title} onChange={(e) => updateLesson(index, { title: e.target.value })} placeholder="Lesson title" maxLength={80} />
              <button type="button" className="icon-ghost" onClick={() => setLessons(lessons.filter((_, i) => i !== index))} aria-label="Remove lesson"><Trash2 size={16} /></button>
            </header>
            <input value={lesson.summary} onChange={(e) => updateLesson(index, { summary: e.target.value })} placeholder="One-line summary" maxLength={200} />
            <div className="editor-columns">
              <label>Key ideas <small>one per line</small>
                <textarea rows={5} value={lesson.keyIdeas} onChange={(e) => updateLesson(index, { keyIdeas: e.target.value })} />
              </label>
              <label>Learning objectives <small>one per line</small>
                <textarea rows={5} value={lesson.objectives} onChange={(e) => updateLesson(index, { objectives: e.target.value })} />
              </label>
              <label>Common misconceptions <small>one per line</small>
                <textarea rows={5} value={lesson.misconceptions} onChange={(e) => updateLesson(index, { misconceptions: e.target.value })} />
              </label>
            </div>
          </article>
        ))}
      </div>

      {error && <p className="form-error" role="alert">{error}</p>}
      <div className="editor-actions">
        <label className="switch-row inline">
          <input type="checkbox" checked={published} onChange={(e) => setPublished(e.target.checked)} />
          <span>Published (visible to students)</span>
        </label>
        <button type="button" className="ghost-button" onClick={onCancel}>Cancel</button>
        <button type="button" className="primary-button" onClick={save} disabled={saving || !lessons.length}>
          {saving && <LoaderCircle className="spin" size={16} />} Save topic
        </button>
      </div>
    </div>
  )
}
