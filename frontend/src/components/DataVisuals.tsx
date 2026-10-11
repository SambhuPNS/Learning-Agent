import type { Visual } from '../types'

const COLORS = ['#1677f2', '#7c5cf0', '#14a37a', '#f08a24']
const WIDTH = 520
const HEIGHT = 300
const MARGIN = { left: 64, right: 18, top: 16, bottom: 58 }
const formatNumber = new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 }).format

function niceTicks(low: number, high: number, count = 5): number[] {
  if (low === high) {
    low -= 1
    high += 1
  }
  const rough = (high - low) / count
  const power = 10 ** Math.floor(Math.log10(rough))
  const step = [1, 2, 5, 10].map((multiple) => multiple * power).find((candidate) => candidate >= rough) ?? 10 * power
  const first = Math.floor(low / step)
  const last = Math.ceil(high / step)
  return Array.from({ length: last - first + 1 }, (_, index) => Number(((first + index) * step).toPrecision(12)))
}

export function BarChart({ visual }: { visual: Visual }) {
  const data = visual.data ?? []
  const low = Math.min(0, ...data.map((bar) => bar.value))
  const high = Math.max(0, ...data.map((bar) => bar.value))
  const position = (value: number) => ((value - low) / (high - low || 1)) * 100
  const zero = position(0)
  return (
    <figure className="visual bar-chart" aria-label={`${visual.caption}. ${data.map((bar) => `${bar.label}: ${formatNumber(bar.value)}`).join(', ')}`}>
      <div className="bar-rows">
        {data.map((bar, index) => (
          <div className="bar-row" key={`${bar.label}-${index}`}>
            <span className="bar-label">{bar.label}</span>
            <div className="bar-track">
              {low < 0 && <span className="bar-zero" style={{ left: `${zero}%` }} />}
              <span
                className="bar-fill"
                style={{
                  left: `${Math.min(zero, position(bar.value))}%`,
                  width: `${Math.abs(position(bar.value) - zero)}%`,
                  background: COLORS[index % COLORS.length],
                }}
              />
            </div>
            <span className="bar-value">{formatNumber(bar.value)}</span>
          </div>
        ))}
      </div>
      {visual.yLabel && <div className="chart-unit">{visual.yLabel}</div>}
      <figcaption>{visual.caption}</figcaption>
    </figure>
  )
}

export function LineGraph({ visual }: { visual: Visual }) {
  const points = visual.points ?? []
  const xTicks = niceTicks(Math.min(...points.map((point) => point.x)), Math.max(...points.map((point) => point.x)))
  const yTicks = niceTicks(Math.min(0, ...points.map((point) => point.y)), Math.max(0, ...points.map((point) => point.y)))
  const [xMin, xMax] = [xTicks[0], xTicks[xTicks.length - 1]]
  const [yMin, yMax] = [yTicks[0], yTicks[yTicks.length - 1]]
  const plotWidth = WIDTH - MARGIN.left - MARGIN.right
  const plotHeight = HEIGHT - MARGIN.top - MARGIN.bottom
  const x = (value: number) => MARGIN.left + ((value - xMin) / (xMax - xMin)) * plotWidth
  const y = (value: number) => MARGIN.top + (1 - (value - yMin) / (yMax - yMin)) * plotHeight
  const describe = (point: { x: number; y: number }) => `(${formatNumber(point.x)}, ${formatNumber(point.y)})`
  return (
    <figure className="visual line-graph">
      <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} className="chart-svg" role="img" aria-label={`${visual.caption}. Points ${points.map(describe).join(', ')}`}>
        {yTicks.map((tick) => (
          <g key={`y${tick}`}>
            <line x1={MARGIN.left} x2={WIDTH - MARGIN.right} y1={y(tick)} y2={y(tick)} className={tick === 0 || tick === yMin ? 'chart-axis' : 'chart-grid'} />
            <text x={MARGIN.left - 8} y={y(tick) + 4} textAnchor="end" className="chart-tick">{formatNumber(tick)}</text>
          </g>
        ))}
        {xTicks.map((tick) => (
          <g key={`x${tick}`}>
            <line x1={x(tick)} x2={x(tick)} y1={MARGIN.top} y2={HEIGHT - MARGIN.bottom} className={tick === 0 || tick === xMin ? 'chart-axis' : 'chart-grid'} />
            <text x={x(tick)} y={HEIGHT - MARGIN.bottom + 20} textAnchor="middle" className="chart-tick">{formatNumber(tick)}</text>
          </g>
        ))}
        <polyline points={points.map((point) => `${x(point.x)},${y(point.y)}`).join(' ')} className="chart-line" />
        {points.map((point, index) => (
          <circle key={index} cx={x(point.x)} cy={y(point.y)} r={5.5} className="chart-point">
            <title>{describe(point)}</title>
          </circle>
        ))}
        {visual.xLabel && <text x={MARGIN.left + plotWidth / 2} y={HEIGHT - 8} textAnchor="middle" className="chart-title">{visual.xLabel}</text>}
        {visual.yLabel && (
          <text transform={`translate(16 ${MARGIN.top + plotHeight / 2}) rotate(-90)`} textAnchor="middle" className="chart-title">{visual.yLabel}</text>
        )}
      </svg>
      <figcaption>{visual.caption}</figcaption>
    </figure>
  )
}

export function DataTable({ visual }: { visual: Visual }) {
  const columns = visual.columns ?? []
  return (
    <figure className="visual table-visual">
      <div className="table-scroll">
        <table className="data-table">
          <thead>
            <tr>{columns.map((column, index) => <th key={index} scope="col">{column}</th>)}</tr>
          </thead>
          <tbody>
            {(visual.rows ?? []).map((row, rowIndex) => (
              <tr key={rowIndex}>{columns.map((_, cellIndex) => <td key={cellIndex}>{row[cellIndex] ?? ''}</td>)}</tr>
            ))}
          </tbody>
        </table>
      </div>
      <figcaption>{visual.caption}</figcaption>
    </figure>
  )
}
