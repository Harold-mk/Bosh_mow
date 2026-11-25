const DOTS = 60 // the ring (docs/regles-design.md)
const RING = Array.from({ length: DOTS }, (_, k) => {
  const angle = (k / DOTS) * 2 * Math.PI - Math.PI / 2 // from the top, clockwise
  return { left: 87.5 + 80 * Math.cos(angle), top: 87.5 + 80 * Math.sin(angle) }
})

type Props = {
  left: number // seconds
  total: number // seconds: the full ring
  label: string // under the time: "restantes", "temps écoulé"
}

/** The time left, in a ring of 60 dots that empties: a small deadline to keep. */
export function Chrono({ left, total, label }: Props) {
  const on = Math.ceil((left / total) * DOTS)
  const minutes = Math.floor(left / 60)
  const seconds = left % 60
  return (
    <div className="ring" role="timer" aria-label={`${minutes} min ${seconds} s restantes`}>
      {RING.map((position, k) => (
        <span key={k} className={k < on ? 'on' : undefined} style={position} />
      ))}
      <div className="ring-center">
        <span className="clock">
          {String(minutes).padStart(2, '0')}:{String(seconds).padStart(2, '0')}
        </span>
        <span className="label">{label}</span>
      </div>
    </div>
  )
}

/** How many questions are done, in figures and in a bar of 20 dots. */
export function Progress({ done, total }: { done: number; total: number }) {
  const filled = total > 0 ? Math.round((done / total) * 20) : 0
  return (
    <div className="progress">
      <div className="progress-head label">
        <span>Questions faites</span>
        <span className="mono">
          {done} / {total}
        </span>
      </div>
      <div className="progress-dots" aria-hidden="true">
        {Array.from({ length: 20 }, (_, k) => (
          <span key={k} className={k < filled ? 'on' : undefined} />
        ))}
      </div>
    </div>
  )
}
