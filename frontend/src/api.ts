import type {
  ClassOverview,
  Health,
  HomeworkExample,
  HomeworkInput,
  HomeworkListItem,
  HomeworkQuestionEdit,
  HomeworkResult,
  HomeworkResults,
  HomeworkStart,
  Insights,
  Profile,
  Role,
  StudentDetail,
  StudentRow,
  Subject,
  TeacherHomework,
  TeacherHomeworkRow,
  TeacherTopic,
  TopicDraft,
  TopicInput,
  TurnAction,
  TurnMeta,
  TurnResponse,
  Understanding,
  UploadedFile,
  UsageReport,
  User,
  WebNotes,
} from './types'

const TOKEN_KEY = 'elevate.token'

export class ApiError extends Error {
  status: number

  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

export const tokenStore = {
  get: () => localStorage.getItem(TOKEN_KEY),
  set: (token: string) => localStorage.setItem(TOKEN_KEY, token),
  clear: () => localStorage.removeItem(TOKEN_KEY),
}

function errorMessage(body: unknown, fallback: string): string {
  const detail = (body as { detail?: unknown } | null)?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail) && detail[0]?.msg) return String(detail[0].msg).replace(/^Value error, /, '')
  return fallback
}

async function request(path: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers)
  const token = tokenStore.get()
  if (token) headers.set('Authorization', `Bearer ${token}`)
  if (init.body && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json')

  let response: Response
  try {
    response = await fetch(`/api${path}`, { ...init, headers })
  } catch (err) {
    if ((err as Error).name === 'AbortError') throw new ApiError(408, 'That took too long.')
    throw new ApiError(0, 'Cannot reach the tutor server. Is the backend running?')
  }
  if (!response.ok) {
    const body = await response.json().catch(() => null)
    throw new ApiError(response.status, errorMessage(body, `Request failed (${response.status})`))
  }
  return response
}

async function json<T>(path: string, init?: RequestInit): Promise<T> {
  return (await request(path, init)).json() as Promise<T>
}

const post = (body: unknown): RequestInit => ({ method: 'POST', body: JSON.stringify(body) })

export const api = {
  health: () => json<Health>('/health'),
  signup: (name: string, email: string, password: string, role: Role, inviteCode: string) =>
    json<{ token: string; user: User }>('/auth/signup', post({ name, email, password, role, inviteCode })),
  login: (email: string, password: string) => json<{ token: string; user: User }>('/auth/login', post({ email, password })),
  googleSignIn: (credential: string, role: Role, inviteCode: string) =>
    json<{ token: string; user: User }>('/auth/google', post({ credential, role, inviteCode })),
  logout: () => json<{ ok: boolean }>('/auth/logout', { method: 'POST' }),
  me: () => json<User>('/me'),
  saveProfile: (profile: Profile) => json<User>('/profile', { method: 'PUT', body: JSON.stringify(profile) }),
  curriculum: () => json<{ subjects: Subject[] }>('/curriculum'),
  insights: () => json<Insights>('/me/insights'),
  turn: (lessonId: string, action: TurnAction, text?: string, meta?: TurnMeta) =>
    json<TurnResponse>('/tutor/turn', post({ lessonId, action, text, meta })),
  prepare: (lessonId: string) => json<{ prepared: boolean }>('/tutor/prepare', post({ lessonId })),
  understand: (lessonId: string, audio: string, signal?: AbortSignal) =>
    json<Understanding>('/speech/understand', { ...post({ lessonId, audio, mimeType: 'audio/wav' }), signal }),
  interpret: (lessonId: string, transcript: string) => json<Understanding>('/speech/interpret', post({ lessonId, transcript })),
  synthesize: async (text: string) => (await request('/speech/synthesize', post({ text }))).blob(),
  teacher: {
    topics: () => json<{ topics: TeacherTopic[] }>('/teacher/topics'),
    draftTopic: (input: { subject: string; title: string; gradeLevel: number; description: string; file?: UploadedFile }) =>
      json<TopicDraft>('/teacher/topics/draft', post(input)),
    fetchNotesUrl: (url: string) => json<WebNotes>('/teacher/topics/fetch-url', post({ url })),
    createTopic: (topic: TopicInput) => json<TeacherTopic>('/teacher/topics', post(topic)),
    updateTopic: (id: string, topic: TopicInput) => json<TeacherTopic>(`/teacher/topics/${encodeURIComponent(id)}`, { method: 'PUT', body: JSON.stringify(topic) }),
    deleteTopic: (id: string) => json<{ ok: boolean }>(`/teacher/topics/${encodeURIComponent(id)}`, { method: 'DELETE' }),
    overview: () => json<ClassOverview>('/teacher/overview'),
    students: () => json<{ students: StudentRow[] }>('/teacher/students'),
    student: (id: string) => json<StudentDetail>(`/teacher/students/${encodeURIComponent(id)}`),
    usage: (days: number) => json<UsageReport>(`/teacher/usage?days=${days}`),
    homework: () => json<{ homework: TeacherHomeworkRow[] }>('/teacher/homework'),
    homeworkDetail: (id: string) => json<TeacherHomework>(`/teacher/homework/${encodeURIComponent(id)}`),
    draftHomework: (lessonId: string, count: number) =>
      json<{ questions: HomeworkQuestionEdit[]; source: 'gemini' | 'outline' }>('/teacher/homework/draft', post({ lessonId, count })),
    createHomework: (input: HomeworkInput) => json<TeacherHomework>('/teacher/homework', post(input)),
    updateHomework: (id: string, input: HomeworkInput) =>
      json<TeacherHomework>(`/teacher/homework/${encodeURIComponent(id)}`, { method: 'PUT', body: JSON.stringify(input) }),
    deleteHomework: (id: string) => json<{ ok: boolean }>(`/teacher/homework/${encodeURIComponent(id)}`, { method: 'DELETE' }),
    homeworkResults: (id: string) => json<HomeworkResults>(`/teacher/homework/${encodeURIComponent(id)}/results`),
  },
  homework: {
    list: () => json<{ homework: HomeworkListItem[] }>('/homework'),
    start: (id: string) => json<HomeworkStart>(`/homework/${encodeURIComponent(id)}/start`, { method: 'POST' }),
    saveAnswer: (id: string, questionId: string, answer: string) =>
      json<{ saved: number }>(`/homework/${encodeURIComponent(id)}/answer`, { method: 'PUT', body: JSON.stringify({ questionId, answer }) }),
    example: (id: string, questionId: string) =>
      json<{ example: HomeworkExample | null }>(`/homework/${encodeURIComponent(id)}/example`, post({ questionId })),
    submit: (id: string, answers: Record<string, string>) => json<HomeworkResult>(`/homework/${encodeURIComponent(id)}/submit`, post({ answers })),
  },
}
