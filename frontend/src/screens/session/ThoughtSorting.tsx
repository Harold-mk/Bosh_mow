import { useState } from 'react'
import type { Thought } from '../../api.ts'

type Props = {
  thoughts: Thought[]
  busy: boolean
  onDecide: (thought: Thought, plannedFor: string | null) => void
}

/** R17: before the session ends, each thought put aside is planned at a precise
 *  moment, or dropped. */
export function ThoughtSorting({ thoughts, busy, onDecide }: Props) {
  return (
    <>
      <div className="statement">
        <span className="label">Parking à pensées</span>
        <h1>Avant de terminer, trie tes pensées</h1>
      </div>
      <p>Planifie chaque pensée à un moment précis, ou abandonne-la. La séance se termine ensuite.</p>
      <ul className="thoughts">
        {thoughts.map((thought) => (
          <ThoughtRow key={thought.id} thought={thought} busy={busy} onDecide={onDecide} />
        ))}
      </ul>
    </>
  )
}

function ThoughtRow({
  thought,
  busy,
  onDecide,
}: {
  thought: Thought
  busy: boolean
  onDecide: Props['onDecide']
}) {
  const [when, setWhen] = useState('') // local date and time, 'YYYY-MM-DDTHH:MM'
  return (
    <li className="thought">
      <span>{thought.text}</span>
      <div className="actions">
        <input
          type="datetime-local"
          className="field"
          value={when}
          onChange={(event) => setWhen(event.target.value)}
          aria-label={`Quand t'en occuper : ${thought.text}`}
        />
        <button
          type="button"
          className="button secondary"
          disabled={busy || !when}
          onClick={() => onDecide(thought, when)}
        >
          Planifier
        </button>
        <button
          type="button"
          className="button ghost"
          disabled={busy}
          onClick={() => onDecide(thought, null)}
        >
          Abandonner
        </button>
      </div>
    </li>
  )
}
