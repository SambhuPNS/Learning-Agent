import { useEffect, useRef, useState, type FormEvent } from 'react'
import {
  ArrowLeft,
  ArrowRight,
  CheckCircle2,
  Ear,
  Lightbulb,
  LoaderCircle,
  MessageCircleQuestion,
  Mic,
  RefreshCw,
  RotateCcw,
  Send,
  Sparkles,
  Square,
  Volume2,
  VolumeX,
  XCircle,
} from 'lucide-react'
import { api } from '../api'
import { FractionVisual } from '../components/FractionVisual'
import { MasteryBar, StrategyBadge } from '../components/Insights'
import { STRATEGY_LABEL } from '../labels'
import type { Health, HistoryItem, Learner, LessonState, LessonSummary, TurnAction, TurnMeta, TurnResponse, TutorStep, Understanding, User } from '../types'
import { browserRecognitionAvailable, recognizeOnce, TutorVoice, UtteranceRecorder } from '../voice'

type VoiceState = 'idle' | 'listening' | 'thinking'
type InputMode = NonNullable<TurnMeta['inputMode']>

const KIND_LABEL: Record<TutorStep['kind'], string> = { teach: 'Learn', question: 'Your turn', feedback: 'Feedback', summary: 'Summary' }
const STUDENT_LABEL: Partial<Record<TurnAction, string>> = {
  continue: "I'm ready, let's continue.",
  hint: 'Can I have a hint?',
  explain_again: 'Can you explain that another way?',
}
const DIFFICULTY_LABEL = { foundation: 'Building foundations', core: 'On track', stretch: 'Ready for a challenge' }

function StepCard({ step, active, speaking, onReplay }: { step: TutorStep; active: boolean; speaking: boolean; onReplay: () => void }) {
  return (
    <article className={`step-card ${step.kind} ${active ? 'active' : ''} ${speaking ? 'speaking' : ''}`}>
      <header>
        <span className={`kind-badge ${step.kind}`}>{KIND_LABEL[step.kind]}</span>
        <h2>{step.title}</h2>
        {step.strategy && <StrategyBadge strategy={step.strategy} />}
        <button type="button" className="icon-ghost" onClick={onReplay} aria-label="Read this aloud" title="Read this aloud">
          {speaking ? <span className="sound-bars" aria-hidden="true"><i /><i /><i /></span> : <Volume2 size={17} />}
        </button>
      </header>
      {step.feedback && (
        <div className={`feedback-banner ${step.feedback.correct ? 'correct' : 'incorrect'}`}>
          {step.feedback.correct ? <CheckCircle2 size={18} /> : <XCircle size={18} />}
          <strong>{step.feedback.correct ? 'Correct answer' : 'Not the right answer yet'}</strong>
        </div>
      )}
      <div className="step-body">
        {step.content?.length ? step.content.map((block, index) => block.type === 'text'
          ? <p key={index}>{block.text}</p>
          : <FractionVisual key={index} visual={block.visual} />)
          : <>
              {step.paragraphs.map((paragraph, index) => <p key={index}>{paragraph}</p>)}
              {step.visual && <FractionVisual visual={step.visual} />}
            </>}
      </div>
      {step.question && (
        <div className="question-callout">
          <MessageCircleQuestion size={18} />
          <p>{step.question.prompt}</p>
        </div>
      )}
    </article>
  )
}

export function LessonScreen({
  user,
  lesson,
  health,
  onExit,
  onAuthError,
}: {
  user: User
  lesson: LessonSummary
  health: Health | null
  onExit: () => void
  onAuthError: (err: unknown) => void
}) {
  const [history, setHistory] = useState<HistoryItem[]>([])
  const [lessonState, setLessonState] = useState<LessonState | null>(null)
  const [learner, setLearner] = useState<Learner | null>(null)
  const [busy, setBusy] = useState(false)
  const [pendingStudent, setPendingStudent] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [draft, setDraft] = useState('')
  const [askMode, setAskMode] = useState(false)
  const [voiceState, setVoiceState] = useState<VoiceState>('idle')
  const [level, setLevel] = useState(0)
  const [heard, setHeard] = useState<Understanding | null>(null)
  const [readAloud, setReadAloud] = useState(user.profile?.voiceEnabled ?? true)
  const [handsFree, setHandsFree] = useState(false)
  const [speakingId, setSpeakingId] = useState<string | null>(null)

  const [voice] = useState(
    () =>
      new TutorVoice((speaking) => {
        if (!speaking) setSpeakingId(null)
      }),
  )
  const recorderRef = useRef<UtteranceRecorder | null>(null)
  const stopRecognitionRef = useRef<(() => void) | null>(null)
  const listeningRef = useRef(false)
  const busyRef = useRef(false)
  const stateRef = useRef<LessonState | null>(null)
  const readAloudRef = useRef(readAloud)
  const handsFreeRef = useRef(handsFree)
  const startedRef = useRef(false)
  const readyAtRef = useRef(performance.now())
  const feedEndRef = useRef<HTMLDivElement>(null)

  const geminiVoice = Boolean(health?.gemini)
  const canListen = geminiVoice || browserRecognitionAvailable()
  const lastTutor = [...history].reverse().find((item): item is Extract<HistoryItem, { role: 'tutor' }> => item.role === 'tutor')?.step
  const question = lessonState?.awaitingAnswer ? lastTutor?.question ?? null : null

  useEffect(() => {
    readAloudRef.current = readAloud
    handsFreeRef.current = handsFree
  }, [readAloud, handsFree])

  useEffect(() => {
    feedEndRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [history.length, pendingStudent, busy])

  useEffect(
    () => () => {
      voice.stop()
      recorderRef.current?.cancel()
      stopRecognitionRef.current?.()
    },
    [voice],
  )

  const speakStep = async (step: TutorStep, force = false) => {
    if (!force && !readAloudRef.current) return
    setSpeakingId(step.id)
    await voice.speak(step.speech, geminiVoice)
  }

  const runTurn = async (action: TurnAction, text?: string, inputMode?: InputMode, responseMs?: number) => {
    if (busyRef.current) return
    busyRef.current = true
    voice.stop()
    setBusy(true)
    setError(null)
    setNotice(null)
    if (action !== 'start' && action !== 'restart') setPendingStudent(text ?? STUDENT_LABEL[action] ?? '')
    const meta: TurnMeta | undefined =
      action === 'start' || action === 'restart'
        ? undefined
        : { responseMs: Math.round(responseMs ?? performance.now() - readyAtRef.current), inputMode }
    let response: TurnResponse
    try {
      response = await api.turn(lesson.id, action, text, meta)
    } catch (err) {
      onAuthError(err)
      setError((err as Error).message)
      return
    } finally {
      busyRef.current = false
      setBusy(false)
      setPendingStudent(null)
    }
    stateRef.current = response.state
    readyAtRef.current = performance.now()
    setHistory(response.history)
    setLessonState(response.state)
    setLearner(response.learner)
    setNotice(response.notice)
    setDraft('')
    setAskMode(false)
    const last = response.history.at(-1)
    if (last?.role !== 'tutor') return
    await speakStep(last.step)
    // Thinking time starts once the tutor has finished speaking.
    if (stateRef.current === response.state) readyAtRef.current = performance.now()
    const stillCurrent = stateRef.current === response.state && !busyRef.current && !listeningRef.current
    if (handsFreeRef.current && readAloudRef.current && !response.state.complete && stillCurrent) void listen()
  }

  const route = (understanding: Understanding, responseMs: number) => {
    switch (understanding.intent) {
      case 'answer':
        return runTurn('answer', understanding.answer, 'voice', responseMs)
      case 'hint':
        return runTurn('hint', undefined, 'voice', responseMs)
      case 'explain_again':
        return runTurn('explain_again', undefined, 'voice', responseMs)
      case 'continue':
        if (stateRef.current?.awaitingAnswer) {
          setNotice("Have a go at the question first. You can also say 'give me a hint'.")
          return
        }
        return runTurn('continue', undefined, 'voice', responseMs)
      case 'ask':
        return runTurn('ask', understanding.question, 'voice', responseMs)
      default:
        setNotice("Sorry, I didn't catch that. Tap the mic and try again.")
    }
  }

  const listen = async () => {
    if (listeningRef.current) {
      recorderRef.current?.stop()
      stopRecognitionRef.current?.()
      return
    }
    if (busyRef.current || !canListen) return
    voice.stop()
    listeningRef.current = true
    const listenStartedAt = performance.now()
    const waitedMs = listenStartedAt - readyAtRef.current
    setHeard(null)
    setError(null)
    setNotice(null)
    setVoiceState('listening')
    try {
      let understanding: Understanding
      let responseMs: number
      if (geminiVoice) {
        const recorder = new UtteranceRecorder()
        recorderRef.current = recorder
        const recording = await recorder.start(setLevel)
        recorderRef.current = null
        listeningRef.current = false
        if (!recording) {
          setVoiceState('idle')
          setNotice("I didn't hear anything. Tap the mic and try again.")
          return
        }
        responseMs = waitedMs + recording.speechStartMs
        setVoiceState('thinking')
        understanding = await api.understand(lesson.id, recording.wavBase64)
      } else {
        const recognition = recognizeOnce()
        stopRecognitionRef.current = recognition.stop
        const transcript = await recognition.result
        stopRecognitionRef.current = null
        listeningRef.current = false
        if (!transcript.trim()) {
          setVoiceState('idle')
          setNotice("I didn't hear anything. Tap the mic and try again.")
          return
        }
        responseMs = performance.now() - readyAtRef.current
        setVoiceState('thinking')
        understanding = await api.interpret(lesson.id, transcript)
      }
      setVoiceState('idle')
      setHeard(understanding)
      await route(understanding, responseMs)
    } catch (err) {
      listeningRef.current = false
      recorderRef.current = null
      setVoiceState('idle')
      onAuthError(err)
      const message = (err as Error).message
      setError(/permission|NotAllowed/i.test(message) ? 'Microphone access was blocked. Allow it in the browser address bar and try again.' : message)
    } finally {
      setLevel(0)
    }
  }

  useEffect(() => {
    if (startedRef.current) return
    startedRef.current = true
    void runTurn('start')
    // Runs once on mount; runTurn reads live values through refs.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const submitDraft = (event: FormEvent) => {
    event.preventDefault()
    const text = draft.trim()
    if (!text) return
    void runTurn(question && !askMode ? 'answer' : 'ask', text, 'typed')
  }

  const toggleReadAloud = () => {
    if (readAloud) voice.stop()
    setReadAloud(!readAloud)
  }

  const disabled = busy || voiceState !== 'idle'
  const progressPercent = lessonState ? Math.min(100, Math.round((lessonState.correct / lessonState.target) * 100)) : 0

  return (
    <div className="lesson-page">
      <header className="lesson-topbar">
        <button type="button" className="ghost-button" onClick={onExit}><ArrowLeft size={16} /> Lessons</button>
        <div className="lesson-title">
          <span>{lesson.topicTitle} · Lesson {lesson.order}</span>
          <strong>{lesson.title}</strong>
        </div>
        <div className="topbar-progress" aria-label={`${progressPercent}% of mastery checks done`}>
          <div className="progress-track"><i style={{ width: `${progressPercent}%` }} /></div>
          <span>{lessonState ? `${lessonState.correct}/${lessonState.target} checks` : '…'}</span>
        </div>
        <button type="button" className="ghost-button" onClick={() => runTurn('restart')} disabled={busy}><RotateCcw size={15} /> Restart</button>
      </header>

      <div className="lesson-layout">
        <main className="lesson-main">
          <div className="feed" aria-live="polite">
            {history.map((item, index) =>
              item.role === 'student' ? (
                <div className="student-bubble" key={`s-${index}`}><span>{item.text}</span></div>
              ) : (
                <StepCard
                  key={item.step.id}
                  step={item.step}
                  active={item.step.id === lastTutor?.id}
                  speaking={speakingId === item.step.id}
                  onReplay={() => (speakingId === item.step.id ? voice.stop() : void speakStep(item.step, true))}
                />
              ),
            )}
            {pendingStudent && <div className="student-bubble pending"><span>{pendingStudent}</span></div>}
            {busy && (
              <div className="thinking-card"><LoaderCircle className="spin" size={18} /> Your tutor is thinking…</div>
            )}
            <div ref={feedEndRef} className="feed-end" />
          </div>

          <section className="dock" aria-label="Your response">
            {(error || notice) && <p className={error ? 'dock-alert error' : 'dock-alert'} role="status">{error ?? notice}</p>}
            {heard && voiceState === 'idle' && (
              <p className="heard"><Ear size={15} /> Heard: “{heard.transcript}”{heard.intent === 'answer' && heard.answer ? <> → <strong>{heard.answer}</strong></> : null}</p>
            )}

            {lessonState?.complete ? (
              <div className="complete-actions">
                <div><Sparkles size={20} /><strong>Lesson complete! Mastery {lessonState.mastery}%</strong></div>
                <button type="button" className="ghost-button" onClick={() => runTurn('restart')}><RotateCcw size={15} /> Practise again</button>
                <button type="button" className="primary-button" onClick={onExit}>Next lesson <ArrowRight size={16} /></button>
              </div>
            ) : (
              <>
                {question && question.format === 'choice' && !askMode && (
                  <div className="choice-answers">
                    {question.options.map((option) => (
                      <button key={option} type="button" className="answer-option" disabled={disabled} onClick={() => runTurn('answer', option, 'choice')}>
                        {option}
                      </button>
                    ))}
                  </div>
                )}

                <div className="dock-row">
                  <button
                    type="button"
                    className={`mic-button ${voiceState}`}
                    onClick={listen}
                    disabled={!canListen || busy || voiceState === 'thinking'}
                    aria-label={voiceState === 'listening' ? 'Stop listening' : 'Speak to your tutor'}
                    title={canListen ? 'Speak to your tutor' : 'Voice input needs Chrome, Edge or Safari, or Vertex AI configured on the backend'}
                    style={{ '--level': level } as React.CSSProperties}
                  >
                    {voiceState === 'thinking' ? <LoaderCircle className="spin" size={22} /> : voiceState === 'listening' ? <Square size={18} fill="currentColor" /> : <Mic size={22} />}
                  </button>

                  {question && (question.format === 'text' || askMode) ? (
                    <form className="answer-form" onSubmit={submitDraft}>
                      <input
                        value={draft}
                        onChange={(e) => setDraft(e.target.value)}
                        placeholder={askMode ? 'Ask your tutor a question…' : 'Type your answer, e.g. 3/8'}
                        aria-label={askMode ? 'Your question' : 'Your answer'}
                        disabled={disabled}
                        maxLength={500}
                      />
                      <button className="primary-button" type="submit" disabled={disabled || !draft.trim()}>
                        {askMode ? 'Ask' : 'Check'} <Send size={15} />
                      </button>
                    </form>
                  ) : question ? (
                    <p className="dock-hint">{voiceState === 'listening' ? 'Listening… say your answer' : 'Pick an answer above, or tap the mic and say it.'}</p>
                  ) : (
                    <form className="answer-form" onSubmit={submitDraft}>
                      <input value={draft} onChange={(e) => setDraft(e.target.value)} placeholder="Ask a question, or press Continue" aria-label="Your question" disabled={disabled} maxLength={500} />
                      {draft.trim() ? (
                        <button className="ghost-button" type="submit" disabled={disabled}>Ask <Send size={15} /></button>
                      ) : (
                        <button className="primary-button" type="button" onClick={() => runTurn('continue', undefined, 'choice')} disabled={disabled || !lessonState}>
                          Continue <ArrowRight size={16} />
                        </button>
                      )}
                    </form>
                  )}
                </div>

                {voiceState === 'listening' && (
                  <div className="listening-bar" aria-hidden="true">
                    <span>Listening — I'll stop when you pause</span>
                    <div className="level"><i style={{ width: `${Math.max(4, level * 100)}%` }} /></div>
                  </div>
                )}
                {voiceState === 'thinking' && <p className="dock-hint">Understanding what you said…</p>}

                <div className="support-row">
                  {question && (
                    <button type="button" className="chip-button amber" onClick={() => runTurn('hint', undefined, 'choice')} disabled={disabled}><Lightbulb size={15} /> Hint</button>
                  )}
                  <button type="button" className="chip-button blue" onClick={() => runTurn('explain_again', undefined, 'choice')} disabled={disabled || !lessonState}><RefreshCw size={15} /> Explain another way</button>
                  {question && (
                    <button type="button" className="chip-button" onClick={() => setAskMode(!askMode)} disabled={disabled}>
                      <MessageCircleQuestion size={15} /> {askMode ? 'Back to answering' : 'Ask a question'}
                    </button>
                  )}
                </div>
              </>
            )}
          </section>
        </main>

        <aside className="lesson-rail" aria-label="Lesson progress and voice settings">
          <section className="rail-card">
            <h3>Your progress</h3>
            <div className="mastery">
              <div className="mastery-ring" style={{ '--mastery': `${(lessonState?.mastery ?? 0) * 3.6}deg` } as React.CSSProperties}>
                <strong>{lessonState?.mastery ?? 0}%</strong>
                <span>mastery</span>
              </div>
              <div>
                <div className="check-dots">
                  {Array.from({ length: lessonState?.target ?? 3 }, (_, i) => <span key={i} className={i < (lessonState?.correct ?? 0) ? 'done' : ''} />)}
                </div>
                <p>{lessonState?.complete ? 'Lesson mastered!' : `Get ${lessonState?.target ?? 3} checks right to master this lesson.`}</p>
              </div>
            </div>
          </section>

          <section className="rail-card">
            <h3>Voice</h3>
            <label className="switch-row">
              <span>{readAloud ? <Volume2 size={16} /> : <VolumeX size={16} />} Read aloud</span>
              <input type="checkbox" role="switch" checked={readAloud} onChange={toggleReadAloud} />
            </label>
            <label className="switch-row">
              <span><Mic size={16} /> Hands-free conversation</span>
              <input type="checkbox" role="switch" checked={handsFree} onChange={() => setHandsFree(!handsFree)} disabled={!canListen || !readAloud} />
            </label>
            <p className="rail-note">
              {handsFree ? 'After the tutor speaks, the mic opens automatically. Just answer out loud.' : 'Tap the mic to answer, ask for a hint, or ask a question out loud.'}
            </p>
            {speakingId && (
              <button type="button" className="ghost-button small" onClick={() => voice.stop()}><Square size={13} /> Stop speaking</button>
            )}
          </section>

          <section className="rail-card">
            <h3>What your tutor knows</h3>
            {learner ? (
              <dl className="profile-list">
                <div><dt>This lesson</dt><dd>{DIFFICULTY_LABEL[learner.difficulty]}</dd></div>
                <div><dt>Teaching style now</dt><dd>{learner.currentStrategy ? STRATEGY_LABEL[learner.currentStrategy] : '—'}</dd></div>
                <div><dt>Works best for you</dt><dd>{STRATEGY_LABEL[learner.bestStrategy]}</dd></div>
                <div><dt>Last answer</dt><dd>{learner.lastResponseSec != null ? `${learner.lastResponseSec}s` : '—'}</dd></div>
                <div><dt>Your average</dt><dd>{learner.avgResponseSec != null ? `${learner.avgResponseSec}s` : '—'}</dd></div>
              </dl>
            ) : (
              <p className="rail-note">Loading…</p>
            )}
            {learner && <MasteryBar value={learner.mastery} />}
            {learner?.watchFor && <p className="watch-for">Working on: {learner.watchFor}</p>}
            <p className={`engine-badge ${geminiVoice ? 'live' : ''}`}>
              <Sparkles size={13} /> {geminiVoice ? `Vertex AI · ${health?.model}` : 'Offline tutor'}
            </p>
          </section>
        </aside>
      </div>
    </div>
  )
}
