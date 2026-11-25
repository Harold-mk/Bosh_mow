import { useState } from 'react'

/** R16: the phone away first; Commencer appears once the box is ticked, and the
 *  session goes full screen. */
export function AwayCheck({ busy, onStart }: { busy: boolean; onStart: () => void }) {
  const [away, setAway] = useState(false)
  return (
    <>
      <label className="check">
        <input type="checkbox" checked={away} onChange={(event) => setAway(event.target.checked)} />
        Téléphone en Ne pas déranger, hors de portée
      </label>
      {away && (
        <div className="actions">
          <button type="button" className="button primary" disabled={busy} onClick={onStart}>
            Commencer
          </button>
          <span className="hint">La séance passe en plein écran.</span>
        </div>
      )}
    </>
  )
}
