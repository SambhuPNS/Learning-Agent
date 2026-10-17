import type { Strategy } from './types'

export const formatDue = (iso: string) => new Date(iso).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' })

export const USAGE_FEATURE_LABEL: Record<string, string> = {
  'tutor.step': 'Lesson steps',
  'tutor.leak_check': 'Answer-leak checks',
  'speech.understand': 'Speech understanding',
  'speech.tts': 'Tutor voice',
  'topic.draft': 'Topic drafting',
  'homework.draft': 'Homework drafting',
  'homework.example': 'Homework examples',
  unknown: 'Other',
}

export const STRATEGY_LABEL: Record<Strategy, string> = {
  visual: 'Visual',
  'step-by-step': 'Step by step',
  'real-world': 'Real-life example',
  practice: 'Worked example',
}
