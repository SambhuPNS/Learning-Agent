import { useCallback, useEffect, useState } from 'react'
import { GraduationCap, Home, LoaderCircle, LogOut, SlidersHorizontal, TriangleAlert } from 'lucide-react'
import { api, ApiError, tokenStore } from './api'
import { AuthScreen } from './screens/AuthScreen'
import { HomeScreen } from './screens/HomeScreen'
import { HomeworkScreen } from './screens/HomeworkScreen'
import { LessonScreen } from './screens/LessonScreen'
import { OnboardingScreen } from './screens/OnboardingScreen'
import { TeacherApp } from './screens/teacher/TeacherApp'
import type { Health, LessonSummary, User } from './types'
import './App.css'

type View = 'loading' | 'auth' | 'onboarding' | 'home' | 'lesson' | 'profile' | 'homework'

const landingView = (user: User): View => (user.role === 'teacher' || user.profile ? 'home' : 'onboarding')

function App() {
  const [view, setView] = useState<View>(() => (tokenStore.get() ? 'loading' : 'auth'))
  const [user, setUser] = useState<User | null>(null)
  const [lesson, setLesson] = useState<LessonSummary | null>(null)
  const [homeworkId, setHomeworkId] = useState<string | null>(null)
  const [health, setHealth] = useState<Health | null>(null)
  const [backendDown, setBackendDown] = useState(false)

  useEffect(() => {
    api.health().then(setHealth).catch(() => setBackendDown(true))
    if (!tokenStore.get()) return
    api
      .me()
      .then((me) => {
        setUser(me)
        setView(landingView(me))
      })
      .catch(() => {
        tokenStore.clear()
        setView('auth')
      })
  }, [])

  const handleAuthError = useCallback((err: unknown) => {
    if (err instanceof ApiError && err.status === 401) {
      tokenStore.clear()
      setUser(null)
      setView('auth')
    }
  }, [])

  // Lessons, homework and the profile page get a browser history entry, so the browser's Back button returns home.
  useEffect(() => {
    const onPop = () => {
      setLesson(null)
      setHomeworkId(null)
      setView((current) => (current === 'lesson' || current === 'profile' || current === 'homework' ? 'home' : current))
    }
    window.addEventListener('popstate', onPop)
    return () => window.removeEventListener('popstate', onPop)
  }, [])

  const openPage = (page: 'lesson' | 'profile' | 'homework') => {
    window.history.pushState({ elevate: page }, '')
    setView(page)
  }

  const backHome = () => {
    if ((window.history.state as { elevate?: string } | null)?.elevate) {
      window.history.back()
      return
    }
    setLesson(null)
    setHomeworkId(null)
    setView('home')
  }

  const signOut = async () => {
    await api.logout().catch(() => undefined)
    tokenStore.clear()
    setUser(null)
    setView('auth')
  }

  const banner = backendDown && (
    <div className="backend-banner"><TriangleAlert size={16} /> The tutor server is not reachable. Start the backend on port 8000 and reload.</div>
  )

  // /api/health decides between Google and password sign-in, so wait for it.
  if (view === 'loading' || (!user && !health && !backendDown)) {
    return <div className="center-screen"><LoaderCircle className="spin" size={26} /></div>
  }

  if (view === 'auth' || !user) {
    return (
      <>
        {banner}
        <AuthScreen
          inviteRequired={Boolean(health?.teacherInviteRequired)}
          googleClientId={health?.googleClientId ?? null}
          onAuthed={(authed) => {
            setUser(authed)
            setView(landingView(authed))
          }}
        />
      </>
    )
  }

  if (user.role === 'teacher') {
    return (
      <>
        {banner}
        <TeacherApp user={user} health={health} onSignOut={signOut} onAuthError={handleAuthError} />
      </>
    )
  }

  if (view === 'onboarding' || view === 'profile') {
    return (
      <OnboardingScreen
        user={user}
        onCancel={view === 'profile' ? backHome : undefined}
        onDone={(updated) => {
          setUser(updated)
          backHome()
        }}
      />
    )
  }

  if (view === 'lesson' && lesson) {
    return (
      <>
        {banner}
        <LessonScreen
          key={lesson.id}
          user={user}
          lesson={lesson}
          health={health}
          onAuthError={handleAuthError}
          onExit={backHome}
        />
      </>
    )
  }

  if (view === 'homework' && homeworkId) {
    return (
      <>
        {banner}
        <HomeworkScreen key={homeworkId} homeworkId={homeworkId} onAuthError={handleAuthError} onExit={backHome} />
      </>
    )
  }

  return (
    <div className="shell">
      {banner}
      <aside className="sidebar">
        <div className="brand-mark">
          <span className="brand-icon"><GraduationCap size={21} /></span>
          <strong>elevate</strong>
        </div>
        <div className="learner-card">
          <span className="avatar-initial">{user.name.charAt(0).toUpperCase()}</span>
          <div><strong>{user.name}</strong><span>{user.email}</span></div>
        </div>
        <nav>
          <button type="button" className="active"><Home size={17} /> Learn</button>
          <button type="button" onClick={() => openPage('profile')}><SlidersHorizontal size={17} /> Learning profile</button>
        </nav>
        <p className={`engine-badge ${health?.gemini ? 'live' : ''}`}>
          {health?.gemini ? `Vertex AI · ${health.model}` : 'Mock tutor (no GCP project configured)'}
        </p>
        <button type="button" className="signout" onClick={signOut}><LogOut size={16} /> Sign out</button>
      </aside>
      <main className="shell-main">
        <HomeScreen
          user={user}
          onAuthError={handleAuthError}
          onOpenLesson={(selected) => {
            setLesson(selected)
            openPage('lesson')
          }}
          onOpenHomework={(id) => {
            setHomeworkId(id)
            openPage('homework')
          }}
        />
      </main>
    </div>
  )
}

export default App
