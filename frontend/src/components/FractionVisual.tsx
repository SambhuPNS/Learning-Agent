import type { Visual, VisualFraction } from '../types'

const COLORS = ['#7c5cf0', '#1677f2', '#14a37a', '#f08a24']

function slicePath(index: number, total: number, radius: number, center: number): string {
  if (total === 1) return `M ${center - radius} ${center} a ${radius} ${radius} 0 1 0 ${radius * 2} 0 a ${radius} ${radius} 0 1 0 ${-radius * 2} 0`
  const start = (index / total) * Math.PI * 2 - Math.PI / 2
  const end = ((index + 1) / total) * Math.PI * 2 - Math.PI / 2
  const x1 = center + radius * Math.cos(start)
  const y1 = center + radius * Math.sin(start)
  const x2 = center + radius * Math.cos(end)
  const y2 = center + radius * Math.sin(end)
  const largeArc = end - start > Math.PI ? 1 : 0
  return `M ${center} ${center} L ${x1} ${y1} A ${radius} ${radius} 0 ${largeArc} 1 ${x2} ${y2} Z`
}

function wholesFor(fraction: VisualFraction) {
  return Math.max(1, Math.ceil(fraction.numerator / fraction.denominator))
}

function FractionCircles({ fraction, color }: { fraction: VisualFraction; color: string }) {
  const wholes = wholesFor(fraction)
  return (
    <div className="visual-wholes">
      {Array.from({ length: wholes }, (_, whole) => {
        const shaded = Math.min(fraction.denominator, Math.max(0, fraction.numerator - whole * fraction.denominator))
        return (
          <svg key={whole} viewBox="0 0 120 120" className="fraction-svg circle" aria-hidden="true">
            {Array.from({ length: fraction.denominator }, (_, index) => (
              <path
                key={index}
                d={slicePath(index, fraction.denominator, 54, 60)}
                fill={index < shaded ? color : '#f3f6fb'}
                stroke="#2d3e58"
                strokeWidth="1.4"
              />
            ))}
          </svg>
        )
      })}
    </div>
  )
}

function FractionBar({ fraction, color }: { fraction: VisualFraction; color: string }) {
  const wholes = wholesFor(fraction)
  return (
    <div className="visual-wholes bars">
      {Array.from({ length: wholes }, (_, whole) => {
        const shaded = Math.min(fraction.denominator, Math.max(0, fraction.numerator - whole * fraction.denominator))
        return (
          <svg key={whole} viewBox="0 0 300 44" className="fraction-svg bar" aria-hidden="true">
            {Array.from({ length: fraction.denominator }, (_, index) => {
              const width = 296 / fraction.denominator
              return (
                <rect
                  key={index}
                  x={2 + index * width}
                  y={2}
                  width={width}
                  height={40}
                  fill={index < shaded ? color : '#f3f6fb'}
                  stroke="#2d3e58"
                  strokeWidth="1.4"
                />
              )
            })}
          </svg>
        )
      })}
    </div>
  )
}

function NumberLine({ fractions }: { fractions: VisualFraction[] }) {
  const max = Math.max(1, ...fractions.map((f) => Math.ceil(f.numerator / f.denominator)))
  const left = 30
  const width = 540
  const x = (value: number) => left + (value / max) * width
  const denominator = fractions[0].denominator
  const ticks = Array.from({ length: max * denominator + 1 }, (_, i) => i / denominator)
  return (
    <svg viewBox="0 0 600 120" className="fraction-svg number-line" role="img" aria-label="Number line">
      <line x1={left} y1={70} x2={left + width} y2={70} stroke="#2d3e58" strokeWidth="2" />
      {ticks.map((value) => {
        const whole = Number.isInteger(value)
        return (
          <g key={value}>
            <line x1={x(value)} y1={whole ? 58 : 63} x2={x(value)} y2={whole ? 82 : 77} stroke="#2d3e58" strokeWidth={whole ? 2 : 1.2} />
            {whole && <text x={x(value)} y={102} textAnchor="middle" className="axis-label">{value}</text>}
          </g>
        )
      })}
      {fractions.map((fraction, index) => {
        const value = fraction.numerator / fraction.denominator
        const color = COLORS[index % COLORS.length]
        return (
          <g key={`${fraction.label}-${index}`}>
            <circle cx={x(value)} cy={70} r={8} fill={color} stroke="#fff" strokeWidth="2" />
            <text x={x(value)} y={40 - (index % 2) * 18} textAnchor="middle" className="point-label" fill={color}>{fraction.label}</text>
          </g>
        )
      })}
    </svg>
  )
}

export function FractionVisual({ visual }: { visual: Visual }) {
  const items = visual.items ?? []
  if (visual.type === 'flow' || visual.type === 'comparison') {
    return (
      <figure className={`visual ${visual.type}`} aria-label={`${visual.caption}. ${items.map((i) => `${i.label}: ${i.detail}`).join('. ')}`}>
        <div className={visual.type === 'flow' ? 'flow-steps' : 'compare-columns'}>
          {items.map((item, index) => (
            <div className="concept-box" key={`${item.label}-${index}`} style={{ borderTopColor: COLORS[index % COLORS.length] }}>
              {visual.type === 'flow' && <span className="flow-index" style={{ background: COLORS[index % COLORS.length] }}>{index + 1}</span>}
              <strong>{item.label}</strong>
              <span>{item.detail}</span>
            </div>
          ))}
        </div>
        <figcaption>{visual.caption}</figcaption>
      </figure>
    )
  }
  const label = `${visual.caption}. Shows ${visual.fractions.map((f) => f.label).join(', ')}`
  if (visual.type === 'number-line') {
    return (
      <figure className="visual" aria-label={label}>
        <NumberLine fractions={visual.fractions} />
        <figcaption>{visual.caption}</figcaption>
      </figure>
    )
  }
  return (
    <figure className={`visual ${visual.type}`} aria-label={label}>
      <div className="visual-items">
        {visual.fractions.map((fraction, index) => {
          const color = COLORS[index % COLORS.length]
          return (
            <div className="visual-item" key={`${fraction.label}-${index}`}>
              {visual.type === 'fraction-circles' ? <FractionCircles fraction={fraction} color={color} /> : <FractionBar fraction={fraction} color={color} />}
              <span className="visual-label" style={{ color }}>{fraction.label}</span>
            </div>
          )
        })}
      </div>
      <figcaption>{visual.caption}</figcaption>
    </figure>
  )
}
