import { useEffect, useMemo, useState } from 'react'
import { BookOpen, Brain, CheckCircle2, ChevronRight, LoaderCircle, PlayCircle, RotateCcw, Sparkles } from 'lucide-react'
import { api } from '../api'
import { BehaviourStats, ConceptList, StrategyChart } from '../components/Insights'
import { STRATEGY_LABEL } from '../labels'
import type { Insights, LessonSummary, Subject, User } from '../types'

type Props = { user: User; onOpenLesson: (lesson: LessonSummary) => void; onAuthError: (err: unknown) => void }

export function HomeScreen({ user, onOpenLesson, onAuthError }: Props) {
  const [subjects, setSubjects] = useState<Subject[] | null>(null)
  const [insights, setInsights] = useState<Insights | null>(null)
  const [subjectId, setSubjectId] = useState<string | null>(null)
  const [topicId, setTopicId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    Promise.all([api.curriculum(), api.insights()])
      .then(([curriculum, learned]) => {
        setSubjects(curriculum.subjects)
        setInsights(learned)
      })
      .catch((err) => {
        onAuthError(err)
        setError((err as Error).message)
      })
  }, [onAuthError])

  const subject = subjects?.find((item) => item.id === subjectId) ?? subjects?.[0]
  const topic = subject?.topics.find((item) => item.id === topicId) ?? subject?.topics[0]
  const allLessons = useMemo(() => subjects?.flatMap((s) => s.topics.flatMap((t) => t.lessons)) ?? [], [subjects])

  const recommended = useMemo(() => {
    const weak = insights?.concepts.filter((c) => c.attempts > 0 && c.mastery < 60).sort((a, b) => a.mastery - b.mastery)[0]
    const weakLesson = weak && allLessons.find((l) => l.id === weak.lessonId && !l.complete)
    if (weakLesson) return { lesson: weakLesson, reason: `Your mastery here is ${weak.mastery}%. A little more practice will lock it in.` }
    const inProgress = allLessons.find((l) => l.started && !l.complete)
    if (inProgress) return { lesson: inProgress, reason: 'Pick up where you left off.' }
    const next = allLessons.find((l) => !l.complete)
    return next ? { lesson: next, reason: 'The next step on your path.' } : null
  }, [insights, allLessons])

  const learned = insights && insights.behaviour.answers > 0

  return (
    <div className="home-grid">
      <div className="home">
        <header className="page-header">
          <p className="eyebrow">Welcome back</p>
          <h1>Hi {user.name.split(' ')[0]}, what shall we learn today?</h1>
        </header>

        {error && <p className="form-error">{error}</p>}
        {!subjects && !error && <p className="muted"><LoaderCircle className="spin" size={16} /> Loading your subjects…</p>}

        {recommended && (
          <section className="recommend-card">
            <div>
              <span className="eyebrow"><Sparkles size={13} /> Recommended for you</span>
              <strong>{recommended.lesson.title}</strong>
              <p>{recommended.lesson.topicTitle} · {recommended.reason}</p>
            </div>
            <button type="button" className="primary-button" onClick={() => onOpenLesson(recommended.lesson)}>
              {recommended.lesson.started ? 'Continue' : 'Start'} <ChevronRight size={16} />
            </button>
          </section>
        )}

        {subjects && subjects.length === 0 && <p className="muted">No topics have been published yet. Ask your teacher to add one.</p>}

        {subject && (
          <>
            <section className="subject-strip" aria-label="Subjects">
              {subjects!.map((item) => (
                <button type="button" key={item.id} className={`subject-card ${item.id === subject.id ? 'active' : ''}`} onClick={() => { setSubjectId(item.id); setTopicId(null) }}>
                  <BookOpen size={20} />
                  <div><strong>{item.title}</strong><span>{item.topics.length} topic{item.topics.length === 1 ? '' : 's'}</span></div>
                </button>
              ))}
            </section>

            <h2 className="section-title">Topics</h2>
            <div className="topic-tabs">
              {subject.topics.map((item) => (
                <button key={item.id} type="button" className={item.id === topic?.id ? 'active' : ''} onClick={() => setTopicId(item.id)}>
                  {item.title}
                </button>
              ))}
            </div>
            {topic?.description && <p className="topic-description">{topic.description}{topic.createdByName ? <span> · by {topic.createdByName}</span> : null}</p>}

            {topic && (
              <div className="lesson-list">
                {topic.lessons.map((lesson) => (
                  <article key={lesson.id} className={`lesson-row ${lesson.id === recommended?.lesson.id ? 'next' : ''}`}>
                    <span className="lesson-index">{lesson.complete ? <CheckCircle2 size={20} /> : lesson.order}</span>
                    <div className="lesson-meta">
                      <strong>{lesson.title}</strong>
                      <span>{lesson.summary}</span>
                      {lesson.started && (
                        <div className="mini-progress" aria-label={`${lesson.mastery}% mastery`}>
                          <i style={{ width: `${lesson.mastery}%` }} />
                        </div>
                      )}
                    </div>
                    <button type="button" className={lesson.id === recommended?.lesson.id ? 'primary-button' : 'ghost-button'} onClick={() => onOpenLesson(lesson)}>
                      {lesson.complete ? <><RotateCcw size={15} /> Review</> : lesson.started ? <><PlayCircle size={15} /> Continue</> : <>Start <ChevronRight size={15} /></>}
                    </button>
                  </article>
                ))}
              </div>
            )}
          </>
        )}
      </div>

      <aside className="home-rail" aria-label="How you learn">
        <section className="rail-card">
          <h3><Brain size={16} /> How you learn</h3>
          {!learned ? (
            <p className="muted small">Your tutor learns how you learn as you answer questions. Finish a few steps and your learning model appears here.</p>
          ) : (
            <>
              <p className="learned-line">
                Works best for you: <strong>{STRATEGY_LABEL[insights!.bestStrategy]}</strong>
              </p>
              <StrategyChart insights={insights!} />
            </>
          )}
        </section>
        {learned && (
          <>
            <section className="rail-card">
              <h3>Your habits</h3>
              <BehaviourStats insights={insights!} />
            </section>
            <section className="rail-card">
              <h3>Mastery by lesson</h3>
              <ConceptList insights={insights!} empty="No lessons practised yet." />
            </section>
          </>
        )}
      </aside>
    </div>
  )
}
