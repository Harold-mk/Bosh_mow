import { useEffect, useEffectEvent, useState } from 'react'
import { messageOf, noteThought, noteWandering } from '../../api.ts'
import { Icon } from '../../components/Icon.tsx'
import { notForShortcuts } from '../../study.ts'

type Props = {
  sessionId: number
  questionId: number | null // the question shown, if any
}

/** Under the chrono: J'ai décroché (R18) and the parking for thoughts (R17), which the
 *  key P also opens, from the question itself. */
export function FocusTools({ sessionId, questionId }: Props) {
  const [parking, setParking] = useState(false)
  const [parked, setParked] = useState(0)
  const [wandered, setWandered] = useState(false)
  const [error, setError] = useState<string>()

  const onKey = useEffectEvent((event: KeyboardEvent) => {
    if (!notForShortcuts(event) && event.key.toLowerCase() === 'p') {
      event.preventDefault() // the P does not go into the field it opens
      setParking(true)
    }
  })
  useEffect(() => {
    const listener = (event: KeyboardEvent) => onKey(event)
    document.addEventListener('keydown', listener)
    return () => document.removeEventListener('keydown', listener)
  }, [])

  useEffect(() => {
    if (!wandered) return
    const timer = setTimeout(() => setWandered(false), 3000)
    return () => clearTimeout(timer)
  }, [wandered])

  async function wander() {
    try {
      setError(undefined)
      await noteWandering(sessionId, questionId)
      setWandered(true)
    } catch (reason) {
      setError(messageOf(reason))
    }
  }

  async function park(text: string) {
    try {
      setError(undefined)
      await noteThought(sessionId, text)
      setParked((n) => n + 1)
      setParking(false)
    } catch (reason) {
      setError(messageOf(reason))
    }
  }

  return (
    <>
      {/* Each one gives the focus back: Entrée goes on with the question. */}
      <div className="side-actions">
        <button
          type="button"
          className="button ghost"
          onClick={(event) => {
            event.currentTarget.blur()
            wander()
          }}
        >
          <Icon name="flag" size={16} />
          J'ai décroché
        </button>
        <button
          type="button"
          className="button ghost"
          onClick={(event) => {
            event.currentTarget.blur()
            setParking(true)
          }}
        >
          <Icon name="note" size={16} />
          Parking à pensées
          {parked > 0 && <span className="mono">{parked}</span>}
        </button>
      </div>
      {wandered && (
        <p className="hint" role="status">
          Décrochage noté : reprends là où tu en étais.
        </p>
      )}
      {error && (
        <p className="hint" role="alert">
          {error}
        </p>
      )}
      {parking && <Parking onPark={park} onClose={() => setParking(false)} />}
    </>
  )
}

/** R17: one line, then back to the question. */
function Parking({ onPark, onClose }: { onPark: (text: string) => void; onClose: () => void }) {
  const [text, setText] = useState('')
  return (
    <form
      className="parking"
      onSubmit={(event) => {
        event.preventDefault()
        if (text.trim()) onPark(text.trim())
      }}
    >
      <input
        className="field"
        autoFocus
        value={text}
        maxLength={200}
        placeholder="Une pensée, en une ligne"
        aria-label="Pensée à mettre de côté"
        onChange={(event) => setText(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === 'Escape') onClose()
        }}
      />
      <span className="hint">Entrée : elle attend la fin de la séance. Échap : retour à la question.</span>
    </form>
  )
}
