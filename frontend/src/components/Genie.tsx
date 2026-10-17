import { useEffect, useLayoutEffect, useRef, useState, type RefObject } from 'react'
import type { TutorVoice } from '../voice'

export type GenieMood = 'idle' | 'thinking' | 'talking' | 'listening' | 'happy' | 'encourage'

const WIDTH = 112
const HEIGHT = 150
const STAR = 'M0 -5 L1.3 -1.3 L5 0 L1.3 1.3 L0 5 L-1.3 1.3 L-5 0 L-1.3 -1.3 Z'

/**
 * Elevate's tutor genie. It floats in a lane beside the lesson, flies to the step being taught, moves its mouth with
 * the tutor's voice, and reacts while Gemini thinks, while the mic listens and after answers. Decorative only.
 */
export function Genie({ mood, bubble, anchor, lane, voice, micLevel }: {
  mood: GenieMood
  bubble: string | null
  anchor: HTMLElement | null
  lane: RefObject<HTMLElement | null>
  voice: TutorVoice
  micLevel: number
}) {
  const rootRef = useRef<HTMLDivElement>(null)
  const mouthRef = useRef<SVGEllipseElement>(null)
  const lastVoiceAt = useRef(0)
  const [place, setPlace] = useState<{ x: number; y: number } | null>(null)

  // Fly beside the newest step; the lane is reserved on wide screens, otherwise the genie docks in a corner.
  useLayoutEffect(() => {
    let frame = 0
    const update = () => {
      cancelAnimationFrame(frame)
      frame = requestAnimationFrame(() => {
        const box = lane.current?.getBoundingClientRect()
        if (!box || window.innerWidth < 1100) {
          setPlace(null)
          return
        }
        const target = anchor?.getBoundingClientRect()
        const top = target ? target.top + 6 : window.innerHeight / 3
        setPlace({ x: box.left + 6, y: Math.min(Math.max(top, 84), window.innerHeight - HEIGHT - 170) })
      })
    }
    update()
    window.addEventListener('resize', update)
    window.addEventListener('scroll', update, true)
    return () => {
      cancelAnimationFrame(frame)
      window.removeEventListener('resize', update)
      window.removeEventListener('scroll', update, true)
    }
  }, [anchor, lane])

  // The mouth follows the voice directly, without re-rendering the lesson on every animation frame.
  useEffect(
    () =>
      voice.listenToLevel((level) => {
        if (level > 0.02) lastVoiceAt.current = performance.now()
        mouthRef.current?.setAttribute('ry', (1.6 + level * 6).toFixed(2))
      }),
    [voice],
  )

  // The browser's fallback voice cannot be measured, so the mouth flaps on its own while it talks.
  useEffect(() => {
    if (mood !== 'talking') return
    const root = rootRef.current
    const timer = window.setInterval(() => root?.classList.toggle('flap', performance.now() - lastVoiceAt.current > 450), 200)
    return () => {
      window.clearInterval(timer)
      root?.classList.remove('flap')
    }
  }, [mood])

  return (
    <div
      ref={rootRef}
      className={`genie ${mood} ${place ? '' : 'docked'}`}
      style={place ? { transform: `translate(${place.x}px, ${place.y}px)` } : undefined}
      aria-hidden="true"
    >
      {bubble && <div className="genie-bubble" key={bubble}>{bubble}</div>}
      <svg viewBox="0 0 120 160" width={WIDTH} height={HEIGHT}>
        <defs>
          <linearGradient id="genie-vest" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="#8b6cf6" />
            <stop offset="1" stopColor="#5b3fd6" />
          </linearGradient>
          <linearGradient id="genie-tail" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="#7c5cf0" />
            <stop offset="1" stopColor="#7c5cf0" stopOpacity="0.15" />
          </linearGradient>
        </defs>
        <g className="genie-float">
          <path className="genie-tail" d="M50 104 C 34 122 66 128 52 146 C 46 153 56 158 64 151" fill="none" stroke="url(#genie-tail)" strokeWidth="15" strokeLinecap="round" />
          <g className="genie-burst" fill="#f6b93b">
            {[[18, 40], [102, 38], [12, 82], [108, 84], [30, 14], [92, 12]].map(([x, y]) => <path key={`${x}-${y}`} d={STAR} transform={`translate(${x} ${y})`} />)}
          </g>
          <g className="genie-arm-left">
            <path d="M40 78 Q 30 88 30 98" fill="none" stroke="#7fb6ff" strokeWidth="8" strokeLinecap="round" />
            <circle cx="30" cy="100" r="5.5" fill="#9cc8ff" />
          </g>
          <path d="M34 104 C 30 82 40 66 60 66 C 80 66 90 82 86 104 C 79 114 41 114 34 104 Z" fill="url(#genie-vest)" />
          <path d="M37 97 Q 60 106 83 97" fill="none" stroke="#f6b93b" strokeWidth="5" strokeLinecap="round" />
          <g className="genie-arm-right">
            <path d="M80 78 Q 90 88 90 98" fill="none" stroke="#7fb6ff" strokeWidth="8" strokeLinecap="round" />
            <circle cx="90" cy="100" r="5.5" fill="#9cc8ff" />
          </g>
          <g className="genie-head">
            <circle cx="36" cy="48" r="5" fill="#7fb6ff" />
            <circle cx="84" cy="48" r="5" fill="#7fb6ff" />
            <circle cx="60" cy="47" r="24" fill="#9cc8ff" />
            <path d="M35 41 C 35 18 85 18 85 41 C 76 34 44 34 35 41 Z" fill="#f6b93b" />
            <path d="M60 22 C 64 12 72 10 76 6" fill="none" stroke="#ff7aa2" strokeWidth="3" strokeLinecap="round" />
            <circle cx="60" cy="31" r="4" fill="#ff5c8a" />
            <g className="genie-eyes">
              <ellipse cx="51" cy="47" rx="5" ry="6" fill="#fff" />
              <ellipse cx="69" cy="47" rx="5" ry="6" fill="#fff" />
              <g className="genie-pupils" fill="#1b2b4b">
                <circle cx="52" cy="48" r="2.7" />
                <circle cx="70" cy="48" r="2.7" />
              </g>
            </g>
            <circle cx="45" cy="57" r="3.5" fill="#ff8fb1" opacity="0.45" />
            <circle cx="75" cy="57" r="3.5" fill="#ff8fb1" opacity="0.45" />
            <path className="genie-smile" d="M53 58 Q 60 64 67 58" fill="none" stroke="#3b1f5e" strokeWidth="2.2" strokeLinecap="round" />
            <ellipse ref={mouthRef} className="genie-mouth" cx="60" cy="60" rx="5.5" ry="1.6" fill="#3b1f5e" />
          </g>
          <g className="genie-orbit" fill="#7c5cf0">
            <path d={STAR} transform="translate(60 6) scale(.8)" />
            <path d={STAR} transform="translate(95 46) scale(.6)" />
            <path d={STAR} transform="translate(25 46) scale(.7)" />
          </g>
          <g className="genie-rings" fill="none" stroke="#7c5cf0" strokeLinecap="round" style={{ transform: `scale(${1 + micLevel * 0.5})` }}>
            <path d="M96 40 Q 102 48 96 56" strokeWidth="2.5" />
            <path d="M101 35 Q 110 48 101 61" strokeWidth="2" opacity="0.6" />
          </g>
        </g>
      </svg>
    </div>
  )
}
