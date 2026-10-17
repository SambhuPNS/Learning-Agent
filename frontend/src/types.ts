export type Strategy = 'visual' | 'step-by-step' | 'real-world' | 'practice'

export type Profile = {
  grade: number
  mathConfidence: number
  fractionsComfort: 'new' | 'some' | 'confident'
  learningStyle: Strategy
  pace: 'slow' | 'steady' | 'fast'
  interests: string[]
  voiceEnabled: boolean
}

export type LessonProgress = { mastery: number; complete: boolean; started: boolean }

export type Role = 'student' | 'teacher'

export type User = {
  id: string
  name: string
  email: string
  role: Role
  profile: Profile | null
  progress: Record<string, LessonProgress>
}

export type LessonSummary = LessonProgress & { id: string; title: string; summary: string; order: number; topicId: string; topicTitle: string }
export type Topic = {
  id: string
  title: string
  gradeLevel: number | null
  description: string
  createdByName: string | null
  available: boolean
  lessons: LessonSummary[]
}
export type Subject = { id: string; title: string; topics: Topic[] }

export type VisualFraction = { numerator: number; denominator: number; label: string }
export type Visual = {
  type: 'fraction-circles' | 'fraction-bars' | 'number-line' | 'flow' | 'comparison' | 'bar-chart' | 'line-graph' | 'table'
  fractions: VisualFraction[]
  items?: { label: string; detail: string }[]
  data?: { label: string; value: number }[]
  points?: { x: number; y: number }[]
  xLabel?: string
  yLabel?: string
  columns?: string[]
  rows?: string[][]
  caption: string
}
export type LessonContent =
  | { type: 'text'; text: string }
  | { type: 'callout'; label: string; text: string }
  | { type: 'visual'; visual: Visual }

export type Question = { prompt: string; format: 'choice' | 'text'; options: string[] }

export type TutorStep = {
  id: string
  kind: 'teach' | 'question' | 'feedback' | 'summary'
  title: string
  paragraphs: string[]
  speech: string
  /** The speech split so its opening plays while the rest is made; older saved steps don't have it. */
  speechParts?: string[]
  visual: Visual | null
  content?: LessonContent[] | null
  feedback: { correct: boolean; message: string } | null
  question: Question | null
  strategy: Strategy | null
  /** Why the tutor chose this step, from the student model (Gemini steps only). */
  why?: string | null
  source: 'gemini' | 'mock'
}

export type TurnAction = 'start' | 'restart' | 'continue' | 'answer' | 'hint' | 'explain_again' | 'ask'

export type HistoryItem =
  | { role: 'tutor'; step: TutorStep }
  | { role: 'student'; action: TurnAction; text: string }

export type LessonState = {
  lessonId: string
  correct: number
  target: number
  mastery: number
  step: number
  estimatedSteps: number
  complete: boolean
  awaitingAnswer: boolean
}

export type Learner = {
  mastery: number
  difficulty: 'foundation' | 'core' | 'stretch'
  currentStrategy: Strategy | null
  bestStrategy: Strategy
  avgResponseSec: number | null
  lastResponseSec: number | null
  watchFor: string | null
}

export type TurnMeta = { responseMs?: number; inputMode?: 'typed' | 'choice' | 'voice' }
export type TurnResponse = { history: HistoryItem[]; state: LessonState; learner: Learner; notice: string | null }

export type SpeechIntent = 'answer' | 'hint' | 'explain_again' | 'continue' | 'ask' | 'unclear'
export type Understanding = { transcript: string; intent: SpeechIntent; answer: string; question: string }

export type Health = { status: string; gemini: boolean; model: string | null; ttsModel: string | null; teacherInviteRequired: boolean; googleClientId: string | null }

export type StrategyStat = {
  strategy: Strategy
  label: string
  score: number
  evidence: number
  uses: number
  success: number
  fail: number
  confused: number
}

export type Insights = {
  overallMastery: number | null
  concepts: { lessonId: string; lessonTitle: string; topicTitle: string; mastery: number; attempts: number; correct: number; avgResponseSec: number | null }[]
  strategies: StrategyStat[]
  bestStrategy: Strategy
  selfReportedStrategy: Strategy | null
  misconceptions: { label: string; count: number; lessonId: string }[]
  behaviour: { answers: number; avgResponseSec: number | null; slowAnswers: number; hintRate: number; explainAgain: number; questionsAsked: number; voiceShare: number }
  recommendations: string[]
  updatedAt: string
}

export type TopicLesson = {
  id?: string
  title: string
  summary: string
  objectives: string[]
  keyIdeas: string[]
  misconceptions: string[]
}

export type TeacherTopic = {
  id: string
  subject: string
  title: string
  gradeLevel: number
  description: string
  createdBy: string
  createdByName: string
  createdAt: string
  updatedAt?: string
  published: boolean
  lessons: TopicLesson[]
  canEdit: boolean
  canDelete: boolean
}

export type TopicInput = Pick<TeacherTopic, 'subject' | 'title' | 'gradeLevel' | 'description' | 'published' | 'lessons'>
export type UploadedFile = { name: string; mimeType: 'application/pdf' | 'text/plain' | 'text/markdown'; data?: string; text?: string }
export type TopicDraft = { summary: string; lessons: TopicLesson[]; source: 'gemini' | 'outline' }

export type StudentRow = {
  id: string
  name: string
  email: string
  grade: number | null
  onboarded: boolean
  overallMastery: number | null
  lessonsStarted: number
  lessonsCompleted: number
  bestStrategy: Strategy | null
  selfReportedStrategy: Strategy | null
  avgResponseSec: number | null
  answers: number
  topMisconception: string | null
  needsSupport: boolean
  lastActive: string | null
}

export type LearningEvent = {
  id: string
  ts: string
  type: string
  lessonTitle?: string
  topicTitle?: string
  [key: string]: unknown
}

export type StudentDetail = { student: User; insights: Insights; events: LearningEvent[] }

export type ClassOverview = {
  studentCount: number
  activeStudents: number
  lessonsCompleted: number
  averageMastery: number | null
  needSupport: number
  concepts: { lessonId: string; lessonTitle: string; topicTitle: string; mastery: number; students: number }[]
  misconceptions: { label: string; count: number; share: number }[]
  strategies: { strategy: Strategy; label: string; attempts: number; successRate: number | null }[]
}
