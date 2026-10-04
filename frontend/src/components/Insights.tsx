import { AlertTriangle, Clock3, Lightbulb, Mic, RefreshCw, Sparkles } from 'lucide-react'
import { STRATEGY_LABEL } from '../labels'
import type { Insights, Strategy } from '../types'

export function StrategyBadge({ strategy }: { strategy: Strategy }) {
  return <span className={`strategy-badge s-${strategy}`}><Sparkles size={11} /> {STRATEGY_LABEL[strategy]}</span>
}

export function MasteryBar({ value }: { value: number }) {
  const tone = value >= 70 ? 'high' : value >= 40 ? 'mid' : 'low'
  return (
    <div className={`mastery-bar ${tone}`} aria-label={`${value}% mastery`}>
      <i style={{ width: `${Math.max(3, value)}%` }} />
    </div>
  )
}

export function StrategyChart({ insights }: { insights: Insights }) {
  return (
    <div className="strategy-chart">
      {insights.strategies.map((item) => (
        <div className="strategy-row" key={item.strategy}>
          <span className="strategy-name">
            {item.label}
            {item.strategy === insights.bestStrategy && item.evidence > 0 && <em>best</em>}
            {item.strategy === insights.selfReportedStrategy && <small>chosen at sign-up</small>}
          </span>
          <div className="strategy-track"><i className={`s-${item.strategy}`} style={{ width: `${item.evidence ? item.score : 0}%` }} /></div>
          <span className="strategy-value">{item.evidence ? `${item.score}%` : '—'}<small>{item.evidence} obs</small></span>
        </div>
      ))}
    </div>
  )
}

export function BehaviourStats({ insights }: { insights: Insights }) {
  const b = insights.behaviour
  return (
    <div className="behaviour-grid">
      <div><Clock3 size={15} /><strong>{b.avgResponseSec ?? '—'}{b.avgResponseSec ? 's' : ''}</strong><span>avg answer time</span></div>
      <div><AlertTriangle size={15} /><strong>{b.slowAnswers}</strong><span>slow answers</span></div>
      <div><Lightbulb size={15} /><strong>{b.hintRate}%</strong><span>hint rate</span></div>
      <div><RefreshCw size={15} /><strong>{b.explainAgain}</strong><span>re-explains</span></div>
      <div><Mic size={15} /><strong>{b.voiceShare}%</strong><span>voice answers</span></div>
    </div>
  )
}

export function ConceptList({ insights, empty }: { insights: Insights; empty: string }) {
  if (!insights.concepts.length) return <p className="muted small">{empty}</p>
  return (
    <ul className="concept-list">
      {insights.concepts.map((concept) => (
        <li key={concept.lessonId}>
          <div>
            <strong>{concept.lessonTitle}</strong>
            <span>{concept.topicTitle} · {concept.correct}/{concept.attempts} correct{concept.avgResponseSec ? ` · ${concept.avgResponseSec}s avg` : ''}</span>
          </div>
          <MasteryBar value={concept.mastery} />
          <b>{concept.mastery}%</b>
        </li>
      ))}
    </ul>
  )
}
