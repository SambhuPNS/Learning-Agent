import { useState } from 'react'
import { BookMarked, ClipboardList, GraduationCap, LayoutDashboard, LogOut, Users } from 'lucide-react'
import type { Health, User } from '../../types'
import { HomeworkView } from './HomeworkView'
import { OverviewView } from './OverviewView'
import { StudentsView } from './StudentsView'
import { TopicsView } from './TopicsView'

type Tab = 'overview' | 'topics' | 'homework' | 'students'

export function TeacherApp({ user, health, onSignOut, onAuthError }: { user: User; health: Health | null; onSignOut: () => void; onAuthError: (err: unknown) => void }) {
  const [tab, setTab] = useState<Tab>('overview')

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand-mark">
          <span className="brand-icon"><GraduationCap size={21} /></span>
          <strong>elevate</strong>
        </div>
        <div className="learner-card">
          <span className="avatar-initial teacher">{user.name.charAt(0).toUpperCase()}</span>
          <div><strong>{user.name}</strong><span>Teacher</span></div>
        </div>
        <nav>
          <button type="button" className={tab === 'overview' ? 'active' : ''} onClick={() => setTab('overview')}><LayoutDashboard size={17} /> Overview</button>
          <button type="button" className={tab === 'topics' ? 'active' : ''} onClick={() => setTab('topics')}><BookMarked size={17} /> Topics</button>
          <button type="button" className={tab === 'homework' ? 'active' : ''} onClick={() => setTab('homework')}><ClipboardList size={17} /> Homework</button>
          <button type="button" className={tab === 'students' ? 'active' : ''} onClick={() => setTab('students')}><Users size={17} /> Students</button>
        </nav>
        <p className={`engine-badge ${health?.gemini ? 'live' : ''}`}>
          {health?.gemini ? `Vertex AI · ${health.model}` : 'Offline mode (no GCP project configured)'}
        </p>
        <button type="button" className="signout" onClick={onSignOut}><LogOut size={16} /> Sign out</button>
      </aside>
      <main className="shell-main">
        {tab === 'overview' && <OverviewView onAuthError={onAuthError} />}
        {tab === 'topics' && <TopicsView onAuthError={onAuthError} />}
        {tab === 'homework' && <HomeworkView onAuthError={onAuthError} />}
        {tab === 'students' && <StudentsView onAuthError={onAuthError} />}
      </main>
    </div>
  )
}
