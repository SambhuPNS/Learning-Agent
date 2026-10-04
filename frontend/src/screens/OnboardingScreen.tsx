import { useState } from 'react'
import { ArrowLeft, ArrowRight, Check, LoaderCircle } from 'lucide-react'
import { api } from '../api'
import type { Profile, User } from '../types'

const CONFIDENCE = ['Not yet', 'A little', 'Okay', 'Good', 'Great']
const COMFORT: { value: Profile['fractionsComfort']; title: string; text: string }[] = [
  { value: 'new', title: 'New to me', text: 'I have not really learned fractions yet.' },
  { value: 'some', title: 'I know some', text: 'I get the basics but get stuck sometimes.' },
  { value: 'confident', title: 'Confident', text: 'I am comfortable and want a challenge.' },
]
const STYLES: { value: Profile['learningStyle']; title: string; text: string }[] = [
  { value: 'visual', title: 'Show me', text: 'Pictures, diagrams and models help me most.' },
  { value: 'step-by-step', title: 'Step by step', text: 'I like clear steps in order.' },
  { value: 'real-world', title: 'Real life', text: 'Stories and everyday examples make it click.' },
  { value: 'practice', title: 'Let me try', text: 'I learn by doing questions quickly.' },
]
const PACES: { value: Profile['pace']; title: string }[] = [
  { value: 'slow', title: 'Take it slow' },
  { value: 'steady', title: 'Steady' },
  { value: 'fast', title: 'Move quickly' },
]
const INTERESTS = ['Football', 'Cricket', 'Music', 'Gaming', 'Cooking', 'Space', 'Animals', 'Art', 'Dance', 'Movies']
const STEPS = ['About you', 'Confidence', 'Learning style', 'Interests']

export function OnboardingScreen({ user, onDone }: { user: User; onDone: (user: User) => void }) {
  const [step, setStep] = useState(0)
  const [profile, setProfile] = useState<Profile>(
    user.profile ?? { grade: 7, mathConfidence: 3, fractionsComfort: 'some', learningStyle: 'visual', pace: 'steady', interests: [], voiceEnabled: true },
  )
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const update = (patch: Partial<Profile>) => setProfile((current) => ({ ...current, ...patch }))

  const toggleInterest = (interest: string) =>
    update({
      interests: profile.interests.includes(interest)
        ? profile.interests.filter((item) => item !== interest)
        : [...profile.interests, interest].slice(0, 4),
    })

  const finish = async () => {
    setBusy(true)
    setError(null)
    try {
      onDone(await api.saveProfile(profile))
    } catch (err) {
      setError((err as Error).message)
      setBusy(false)
    }
  }

  return (
    <div className="onboarding-page">
      <div className="onboarding-card">
        <ol className="stepper" aria-label="Profile steps">
          {STEPS.map((label, index) => (
            <li key={label} className={index === step ? 'current' : index < step ? 'done' : ''}>
              <span>{index < step ? <Check size={13} /> : index + 1}</span>
              {label}
            </li>
          ))}
        </ol>

        {step === 0 && (
          <section>
            <h1>Hi {user.name.split(' ')[0]}, let's set up your tutor.</h1>
            <p className="lead">Your answers shape every lesson. You can change them later.</p>
            <h2>Which grade are you in?</h2>
            <div className="choice-row">
              {[4, 5, 6, 7, 8, 9, 10].map((grade) => (
                <button key={grade} type="button" className={`pill ${profile.grade === grade ? 'selected' : ''}`} onClick={() => update({ grade })}>
                  Grade {grade}
                </button>
              ))}
            </div>
          </section>
        )}

        {step === 1 && (
          <section>
            <h1>How do you feel about maths?</h1>
            <p className="lead">There is no wrong answer. This just sets the starting point.</p>
            <h2>Maths in general</h2>
            <div className="choice-row">
              {CONFIDENCE.map((label, index) => (
                <button key={label} type="button" className={`pill ${profile.mathConfidence === index + 1 ? 'selected' : ''}`} onClick={() => update({ mathConfidence: index + 1 })}>
                  {label}
                </button>
              ))}
            </div>
            <h2>Fractions</h2>
            <div className="option-grid three">
              {COMFORT.map((item) => (
                <button key={item.value} type="button" className={`option-card ${profile.fractionsComfort === item.value ? 'selected' : ''}`} onClick={() => update({ fractionsComfort: item.value })}>
                  <strong>{item.title}</strong>
                  <span>{item.text}</span>
                </button>
              ))}
            </div>
          </section>
        )}

        {step === 2 && (
          <section>
            <h1>How do you learn best?</h1>
            <p className="lead">Your tutor will explain things this way first.</p>
            <div className="option-grid">
              {STYLES.map((item) => (
                <button key={item.value} type="button" className={`option-card ${profile.learningStyle === item.value ? 'selected' : ''}`} onClick={() => update({ learningStyle: item.value })}>
                  <strong>{item.title}</strong>
                  <span>{item.text}</span>
                </button>
              ))}
            </div>
            <h2>Pace</h2>
            <div className="choice-row">
              {PACES.map((item) => (
                <button key={item.value} type="button" className={`pill ${profile.pace === item.value ? 'selected' : ''}`} onClick={() => update({ pace: item.value })}>
                  {item.title}
                </button>
              ))}
            </div>
          </section>
        )}

        {step === 3 && (
          <section>
            <h1>What do you enjoy?</h1>
            <p className="lead">Pick up to 4. Your tutor will use them in examples.</p>
            <div className="choice-row">
              {INTERESTS.map((interest) => (
                <button key={interest} type="button" className={`pill ${profile.interests.includes(interest) ? 'selected' : ''}`} onClick={() => toggleInterest(interest)}>
                  {interest}
                </button>
              ))}
            </div>
            <label className="toggle-row">
              <input type="checkbox" checked={profile.voiceEnabled} onChange={(e) => update({ voiceEnabled: e.target.checked })} />
              <span>
                <strong>Read lessons aloud</strong>
                The tutor speaks each explanation and question.
              </span>
            </label>
          </section>
        )}

        {error && <p className="form-error" role="alert">{error}</p>}
        <div className="onboarding-actions">
          <button type="button" className="ghost-button" onClick={() => setStep(step - 1)} disabled={step === 0 || busy}>
            <ArrowLeft size={16} /> Back
          </button>
          {step < STEPS.length - 1 ? (
            <button type="button" className="primary-button" onClick={() => setStep(step + 1)}>
              Next <ArrowRight size={16} />
            </button>
          ) : (
            <button type="button" className="primary-button" onClick={finish} disabled={busy}>
              {busy && <LoaderCircle className="spin" size={16} />} Start learning
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
