type Props = {
  label: string
  value: number | string
  unit?: string
  context?: string // one line under the number
}

/** A key figure (docs/regles-design.md): the number first, in JetBrains Mono 40 px.
 *  Two or three per screen at most. */
export function KeyFigure({ label, value, unit, context }: Props) {
  return (
    <div className="card key-figure">
      <span className="label">{label}</span>
      <span className="key-figure-value">
        <span className="key-figure-number">{value}</span>
        {unit && <span className="key-figure-unit">{unit}</span>}
      </span>
      {context && <span className="hint">{context}</span>}
    </div>
  )
}
