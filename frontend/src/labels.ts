import type { Strategy } from './types'

export const formatDue = (iso: string) => new Date(iso).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' })

export const STRATEGY_LABEL: Record<Strategy, string> = {
  visual: 'Visual',
  'step-by-step': 'Step by step',
  'real-world': 'Real-life example',
  practice: 'Worked example',
}
