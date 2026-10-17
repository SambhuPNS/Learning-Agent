import { useEffect, useMemo, useRef, useState } from 'react'
import { ArrowLeft, ArrowRight, CheckCircle2, Clock, LoaderCircle, Send, Sparkles, XCircle } from 'lucide-react'
import { api } from '../api'
import { formatDue, STRATEGY_LABEL } from '../labels'
import type { HomeworkExample, HomeworkQuestion, HomeworkResult, HomeworkStart } from '../types'
import { ContentBlock } from './LessonScreen'

type Quiz = Extract<HomeworkStart, { submitted: false }>['homework']

function verdict(percent: number) {
  if (percent === 100) return 'Perfect score. Brilliant work!'
  if (percent >= 80) return 'Great work. You know this well.'
  if (percent >= 50) return 'Good effort. Look at the explanations below to close the gaps.'
  return 'This one was tricky. Read the explanations below, then try the lesson again with your tutor.'
}

function Results({ result, onExit }: { result: HomeworkResult; onExit: () => void }) {
  const percent = Math.round((100 * result.score) / Math.max(1, result.total))
  return (
    <div className="hw-results">
      <section className="panel hw-score">
        <div className="hw-score-number"><strong>{result.score}</strong><span>/ {result.total}</span></div>
        <div>
          <h2>{percent}% correct{result.late && <span className="hw-chip late">Handed in late</span>}</h2>
          <p className="muted">{verdict(percent)}</p>
        </div>
      </section>
      <h3 className="section-title">Review your answers</h3>
      <div className="hw-review">
        {result.review.map((item, index) => (
          <article key={item.questionId} className={`panel hw-review-item ${item.correct ? 'correct' : 'incorrect'}`}>
            <header>
              {item.correct ? <CheckCircle2 size={19} /> : <XCircle size={19} />}
              <strong>{index + 1}. {item.prompt}</strong>
            </header>
            <p><span className="muted">Your answer:</span> <strong>{item.yourAnswer}</strong></p>
            {!item.correct && <p><span className="muted">Correct answer:</span> <strong>{item.correctAnswer}</strong></p>}
            {item.explanation && <p className="hw-explain">{item.explanation}</p>}
          </article>
        ))}
      </div>
      <button type="button" className="primary-button" onClick={onExit}>Back to home</button>
    </div>
  )
}

function ExampleCard({ example }: { example: HomeworkExample | null | 'loading' | undefined }) {
  if (example === 'loading') {
    return <section className="panel hw-example loading" aria-live="polite"><LoaderCircle className="spin" size={16} /> Your tutor is preparing an example…</section>
  }
  if (!example) return null
  return (
    <section className="panel hw-example" aria-label="Example from your tutor">
      <header>
        <span className="eyebrow"><Sparkles size={13} /> Before you answer</span>
        <span className="hw-chip">{STRATEGY_LABEL[example.strategy]}</span>
      </header>
      <h3>{example.title}</h3>
      <div className="step-body">{example.content.map((block, i) => <ContentBlock key={i} block={block} />)}</div>
      {example.why && <p className="step-why"><Sparkles size={14} aria-hidden="true" /> <span><strong>Why this example:</strong> {example.why}</span></p>}
    </section>
  )
}

function Question({ question, value, onChange, onCommit }: { question: HomeworkQuestion; value: string; onChange: (value: string) => void; onCommit: (value: string) => void }) {
  if (question.format === 'choice') {
    return (
      <div className="hw-options" role="radiogroup" aria-label={question.prompt}>
        {question.options.map((option) => (
          <button key={option} type="button" role="radio" aria-checked={value === option} className={value === option ? 'selected' : ''}
            onClick={() => { onChange(option); onCommit(option) }}>
            {option}
          </button>
        ))}
      </div>
    )
  }
  return (
    <input className="hw-text" value={value} maxLength={300} placeholder="Type your answer" aria-label="Your answer"
      onChange={(e) => onChange(e.target.value)} onBlur={() => onCommit(value)} />
  )
}

export function HomeworkScreen({ homeworkId, onExit, onAuthError }: { homeworkId: string; onExit: () => void; onAuthError: (err: unknown) => void }) {
  const [quiz, setQuiz] = useState<Quiz | null>(null)
  const [answers, setAnswers] = useState<Record<string, string>>({})
  const [index, setIndex] = useState(0)
  const [result, setResult] = useState<HomeworkResult | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const saved = useRef<Record<string, string>>({})
  const [examples, setExamples] = useState<Record<string, HomeworkExample | null | 'loading'>>({})
  const requested = useRef<Set<string>>(new Set())

  useEffect(() => {
    api.homework.start(homeworkId)
      .then((data) => {
        if (data.submitted) {
          setResult(data.result)
          return
        }
        setQuiz(data.homework)
        setAnswers(data.answers)
        saved.current = { ...data.answers }
        const firstOpen = data.homework.questions.findIndex((q) => !data.answers[q.id])
        setIndex(firstOpen === -1 ? 0 : firstOpen)
      })
      .catch((err) => {
        onAuthError(err)
        setError((err as Error).message)
      })
  }, [homeworkId, onAuthError])

  // The tutor prepares the example for this question and the next one while the student works.
  useEffect(() => {
    if (!quiz) return
    for (const q of quiz.questions.slice(index, index + 2)) {
      if (requested.current.has(q.id)) continue
      requested.current.add(q.id)
      setExamples((current) => ({ ...current, [q.id]: 'loading' }))
      api.homework.example(homeworkId, q.id)
        .then((data) => setExamples((current) => ({ ...current, [q.id]: data.example })))
        .catch(() => setExamples((current) => ({ ...current, [q.id]: null })))
    }
  }, [quiz, index, homeworkId])

  const commit = (questionId: string, value: string) => {
    if (!value.trim() || saved.current[questionId] === value) return
    saved.current[questionId] = value
    api.homework.saveAnswer(homeworkId, questionId, value).catch(() => undefined)
  }

  const unanswered = useMemo(() => quiz?.questions.filter((q) => !answers[q.id]?.trim()).length ?? 0, [quiz, answers])

  const submit = async () => {
    setSubmitting(true)
    setError(null)
    try {
      setResult(await api.homework.submit(homeworkId, answers))
      window.scrollTo({ top: 0 })
    } catch (err) {
      onAuthError(err)
      setError((err as Error).message)
    } finally {
      setSubmitting(false)
    }
  }

  const header = (
    <header className="hw-topbar">
      <button type="button" className="ghost-button" onClick={onExit}><ArrowLeft size={15} /> Home</button>
      <div>
        {quiz && <span className="muted small">{quiz.topicTitle} · {quiz.lessonTitle}</span>}
        <strong>{quiz?.title ?? result?.title ?? 'Homework'}</strong>
      </div>
      {quiz && <span className="hw-due"><Clock size={14} /> Due {formatDue(quiz.dueAt)}</span>}
    </header>
  )

  if (result) return <div className="hw-page">{header}<Results result={result} onExit={onExit} /></div>
  if (error && !quiz) return <div className="hw-page">{header}<p className="form-error">{error}</p></div>
  if (!quiz) return <div className="hw-page">{header}<p className="muted"><LoaderCircle className="spin" size={16} /> Opening your homework…</p></div>

  const question = quiz.questions[index]
  const last = index === quiz.questions.length - 1

  return (
    <div className="hw-page">
      {header}
      {index === 0 && quiz.instructions && <p className="hw-instructions">{quiz.instructions}</p>}
      <nav className="hw-steps" aria-label="Questions">
        {quiz.questions.map((q, i) => (
          <button key={q.id} type="button" className={`${i === index ? 'current' : ''} ${answers[q.id]?.trim() ? 'answered' : ''}`}
            onClick={() => { commit(question.id, answers[question.id] ?? ''); setIndex(i) }} aria-label={`Question ${i + 1}${answers[q.id]?.trim() ? ', answered' : ''}`}>
            {i + 1}
          </button>
        ))}
      </nav>
      <ExampleCard example={examples[question.id]} />
      <section className="panel hw-card">
        <p className="eyebrow">Question {index + 1} of {quiz.questions.length}</p>
        <h2>{question.prompt}</h2>
        <Question question={question} value={answers[question.id] ?? ''}
          onChange={(value) => setAnswers((current) => ({ ...current, [question.id]: value }))}
          onCommit={(value) => commit(question.id, value)} />
      </section>
      {error && <p className="form-error">{error}</p>}
      <div className="hw-actions">
        <button type="button" className="ghost-button" disabled={index === 0} onClick={() => { commit(question.id, answers[question.id] ?? ''); setIndex(index - 1) }}>
          <ArrowLeft size={15} /> Back
        </button>
        {last ? (
          <div className="hw-submit">
            {unanswered > 0 && <span className="muted small">{unanswered} question{unanswered === 1 ? '' : 's'} still to answer</span>}
            <button type="button" className="primary-button" disabled={unanswered > 0 || submitting} onClick={() => void submit()}>
              {submitting ? <LoaderCircle className="spin" size={16} /> : <Send size={16} />} Hand in homework
            </button>
          </div>
        ) : (
          <button type="button" className="primary-button" onClick={() => { commit(question.id, answers[question.id] ?? ''); setIndex(index + 1) }}>
            Next <ArrowRight size={16} />
          </button>
        )}
      </div>
    </div>
  )
}
