import { useState, type FormEvent } from 'react'
import { BookOpenCheck, GraduationCap, LoaderCircle, School } from 'lucide-react'
import { api, tokenStore } from '../api'
import { GoogleSignInButton } from '../components/GoogleSignInButton'
import type { Role, User } from '../types'

export function AuthScreen({ onAuthed, inviteRequired, googleClientId }: {
  onAuthed: (user: User) => void
  inviteRequired: boolean
  googleClientId: string | null
}) {
  const [mode, setMode] = useState<'signup' | 'login'>('signup')
  const [role, setRole] = useState<Role>('student')
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [inviteCode, setInviteCode] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const authenticate = async (attempt: () => Promise<{ token: string; user: User }>) => {
    setError(null)
    setBusy(true)
    try {
      const result = await attempt()
      tokenStore.set(result.token)
      onAuthed(result.user)
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    await authenticate(() => (mode === 'signup' ? api.signup(name, email, password, role, inviteCode) : api.login(email, password)))
  }

  const continueWithGoogle = (credential: string) => {
    if (!busy) authenticate(() => api.googleSignIn(credential, role, inviteCode))
  }

  const rolePicker = (
    <div className="role-picker" role="radiogroup" aria-label="I am a">
      <button type="button" role="radio" aria-checked={role === 'student'} className={role === 'student' ? 'active' : ''} onClick={() => setRole('student')}>
        <BookOpenCheck size={18} /><strong>Student</strong><span>Learn with my tutor</span>
      </button>
      <button type="button" role="radio" aria-checked={role === 'teacher'} className={role === 'teacher' ? 'active' : ''} onClick={() => setRole('teacher')}>
        <School size={18} /><strong>Teacher</strong><span>Create topics, see insights</span>
      </button>
    </div>
  )

  return (
    <div className="auth-page">
      <section className="auth-intro">
        <div className="brand-mark light">
          <span className="brand-icon"><GraduationCap size={22} /></span>
          <strong>brightpath</strong>
        </div>
        <h1>A tutor that learns how you learn.</h1>
        <p>Short lessons that explain first, then check your thinking. Answer by typing or just talk to your tutor.</p>
        <ul>
          <li>Lessons shaped around your pace and interests</li>
          <li>Visual explanations you can hear and read</li>
          <li>Instant feedback, hints and new ways to explain</li>
        </ul>
      </section>

      {googleClientId ? (
        <div className="auth-card">
          <h2>Welcome to brightpath</h2>
          <p className="auth-note">New here? Choose student or teacher, then continue with Google. Already have an account? Just continue.</p>
          {rolePicker}
          {role === 'teacher' && inviteRequired && (
            <label>
              Teacher invite code (first sign-in only)
              <input value={inviteCode} onChange={(e) => setInviteCode(e.target.value)} maxLength={64} autoComplete="off" />
            </label>
          )}
          {error && <p className="form-error" role="alert">{error}</p>}
          <GoogleSignInButton clientId={googleClientId} onCredential={continueWithGoogle} onError={setError} />
          {busy && <p className="muted"><LoaderCircle className="spin" size={16} /> Signing you in…</p>}
        </div>
      ) : (
        <form className="auth-card" onSubmit={submit}>
          <div className="segmented" role="tablist">
            <button type="button" role="tab" aria-selected={mode === 'signup'} className={mode === 'signup' ? 'active' : ''} onClick={() => setMode('signup')}>Create account</button>
            <button type="button" role="tab" aria-selected={mode === 'login'} className={mode === 'login' ? 'active' : ''} onClick={() => setMode('login')}>Sign in</button>
          </div>
          <h2>{mode === 'signup' ? 'Create your account' : 'Welcome back'}</h2>
          {mode === 'signup' && rolePicker}
          {mode === 'signup' && (
            <label>
              Your name
              <input value={name} onChange={(e) => setName(e.target.value)} required maxLength={60} autoComplete="name" placeholder="Maya Rao" />
            </label>
          )}
          <label>
            Email
            <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required autoComplete="email" placeholder="you@example.com" />
          </label>
          <label>
            Password
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              minLength={mode === 'signup' ? 8 : 1}
              autoComplete={mode === 'signup' ? 'new-password' : 'current-password'}
              placeholder={mode === 'signup' ? 'At least 8 characters' : ''}
            />
          </label>
          {mode === 'signup' && role === 'teacher' && inviteRequired && (
            <label>
              Teacher invite code
              <input value={inviteCode} onChange={(e) => setInviteCode(e.target.value)} required maxLength={64} autoComplete="off" />
            </label>
          )}
          {error && <p className="form-error" role="alert">{error}</p>}
          <button className="primary-button wide" type="submit" disabled={busy}>
            {busy && <LoaderCircle className="spin" size={17} />}
            {mode === 'signup' ? `Create ${role} account` : 'Sign in'}
          </button>
        </form>
      )}
    </div>
  )
}
