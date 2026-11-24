import { useEffect, useState } from 'react'
import { askProposal, getProposal, messageOf, type ProposalState } from '../../api.ts'
import { Notice } from '../../components/Notice.tsx'

const FOLLOW_MS = 3000 // how often the page asks where the proposal stands

/** The split into chapters of a subject validated without it (R2): where Claude's
 *  proposal stands, followed until it is ready or has failed. */
export function PendingSplit({ subjectId }: { subjectId: number }) {
  const [state, setState] = useState<ProposalState>()
  const [error, setError] = useState<string>()
  const [request, setRequest] = useState(0) // a new request restarts the follow-up

  useEffect(() => {
    let stopped = false
    let timer = 0
    async function follow() {
      try {
        const current = await getProposal(subjectId)
        if (stopped) return
        setState(current)
        setError(undefined)
        if (current.status === 'pending' || current.status === 'running') {
          timer = window.setTimeout(follow, FOLLOW_MS)
        }
      } catch (reason) {
        if (!stopped) setError(messageOf(reason))
      }
    }
    follow()
    return () => {
      stopped = true
      window.clearTimeout(timer)
    }
  }, [subjectId, request])

  async function ask() {
    try {
      await askProposal(subjectId)
      setRequest((n) => n + 1)
    } catch (reason) {
      setError(messageOf(reason))
    }
  }

  const askButton = (label: string) => (
    <button type="button" className="button secondary" onClick={ask}>
      {label}
    </button>
  )

  if (error) {
    return (
      <div className="pending-split">
        <Notice>{error}</Notice>
        {askButton('Demander le découpage à Claude')}
      </div>
    )
  }
  if (!state) return null
  if (state.status === 'done') {
    return (
      <div className="pending-split">
        <p>La proposition de découpage est prête.</p>
      </div>
    )
  }
  if (state.status === 'failed') {
    return (
      <div className="pending-split">
        <p>La proposition de Claude n'a pas passé les contrôles.</p>
        <span className="hint">Détail : {state.error}</span>
        {askButton('Redemander une proposition')}
      </div>
    )
  }
  if (state.status === 'pending' && state.error) {
    return (
      <div className="pending-split">
        <p>
          Claude n'est pas disponible pour l'instant : {state.error} Bosh mow réessaiera
          tout seul dans quelques minutes.
        </p>
        {askButton('Réessayer maintenant')}
      </div>
    )
  }
  return (
    <div className="pending-split">
      <p>
        Claude prépare le découpage en chapitres. Tu peux quitter cette page : il continue
        en arrière-plan.
      </p>
    </div>
  )
}
