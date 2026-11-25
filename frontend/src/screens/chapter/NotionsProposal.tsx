import { type FormEvent, type ReactNode, useEffect, useState } from 'react'
import {
  askPreparation,
  type ChapterView,
  getPreparation,
  messageOf,
  type PreparationState,
  type Resource,
  validateNotions,
} from '../../api.ts'
import { Notice } from '../../components/Notice.tsx'
import { count, pagesOf } from '../../format.ts'

const FOLLOW_MS = 3000 // how often to ask where the proposal stands while Claude works

type Props = {
  subjectId: number
  chapter: ChapterView
  files: Resource[]
  onValidated: (chapter: ChapterView) => void
}

/** Before the notions of a chapter are validated (R3): where Claude's proposal stands
 *  (T1 pass 2), asking again every few seconds while Claude works, then the notions
 *  to check and validate. */
export function NotionsProposal({ subjectId, chapter, files, onValidated }: Props) {
  const [state, setState] = useState<PreparationState | null>()
  const [error, setError] = useState<string>()
  const [request, setRequest] = useState(0) // a new request restarts the follow-up

  useEffect(() => {
    let stopped = false
    let timer = 0
    async function follow() {
      try {
        const current = await getPreparation(subjectId, chapter.number)
        if (stopped) return
        setState(current)
        setError(undefined)
        if (current?.status === 'pending' || current?.status === 'running') {
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
  }, [subjectId, chapter.number, request])

  async function ask() {
    try {
      setState(await askPreparation(subjectId, chapter.number))
      setError(undefined)
      setRequest((n) => n + 1)
    } catch (reason) {
      setError(messageOf(reason))
    }
  }

  const askButton = (label: string, primary = false) => (
    <button type="button" className={`button ${primary ? 'primary' : 'secondary'}`} onClick={ask}>
      {label}
    </button>
  )

  if (error) {
    return (
      <Waiting>
        <Notice>{error}</Notice>
        {askButton('Redemander les notions')}
      </Waiting>
    )
  }
  if (state === undefined) return null
  if (state === null) {
    return (
      <Waiting>
        <p>
          Les notions de ce chapitre n'ont pas encore été proposées. Claude les découpe
          juste avant que tu étudies le chapitre, mais tu peux les demander dès maintenant.
        </p>
        {askButton('Préparer ce chapitre', true)}
      </Waiting>
    )
  }
  if (state.status === 'done') {
    return (
      <NotionsForm
        subjectId={subjectId}
        chapter={chapter}
        proposal={state}
        files={files}
        onValidated={onValidated}
      />
    )
  }
  if (state.status === 'failed') {
    return (
      <Waiting>
        <p>La proposition de Claude n'a pas passé les contrôles.</p>
        <details className="detail">
          <summary>Détail</summary>
          {state.error}
        </details>
        {askButton('Redemander les notions')}
      </Waiting>
    )
  }
  if (state.status === 'pending' && state.error) {
    return (
      <Waiting>
        <p>
          En attente : {state.error} Bosh mow réessaiera tout seul dans quelques minutes.
        </p>
        {askButton('Réessayer maintenant')}
      </Waiting>
    )
  }
  return (
    <Waiting>
      <p>
        Claude découpe le chapitre en notions. Tu peux quitter cette page : il continue en
        arrière-plan.
      </p>
    </Waiting>
  )
}

function Waiting({ children }: { children: ReactNode }) {
  return (
    <section className="card chapter-section">
      <h2>Notions</h2>
      <div className="chapter-waiting">{children}</div>
    </section>
  )
}

type FormProps = {
  subjectId: number
  chapter: ChapterView
  proposal: PreparationState
  files: Resource[]
  onValidated: (chapter: ChapterView) => void
}

/** The notions proposed, their titles to check (R3); Claude then writes their
 *  questions. Merging or splitting notions comes later. */
function NotionsForm({ subjectId, chapter, proposal, files, onValidated }: FormProps) {
  const [titles, setTitles] = useState(() => proposal.notions.map((notion) => notion.title))
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string>()
  const several = new Set(proposal.notions.map((notion) => notion.resource_id)).size > 1
  const ready = !busy && titles.every((title) => title.trim() !== '')

  async function submit(event: FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError(undefined)
    try {
      onValidated(await validateNotions(subjectId, chapter.number, titles))
    } catch (reason) {
      setError(messageOf(reason))
      setBusy(false)
    }
  }

  return (
    <form className="card chapter-section" onSubmit={submit}>
      <h2>Notions proposées</h2>
      <p>
        Claude propose {count(proposal.notions.length, 'notion')}, chacune à lire en 10
        minutes au plus. Corrige leurs titres si besoin, puis valide : il écrira ensuite les
        questions de chacune.
      </p>
      {proposal.boundary_alert && (
        <p className="boundary">
          <strong>Limites du chapitre à vérifier.</strong> {proposal.boundary_alert}
        </p>
      )}
      <ol className="chapter-list">
        {proposal.notions.map((notion, k) => (
          <li key={k} className="notion-proposed">
            <span className="mono chapter-number">
              {chapter.number}.{k + 1}
            </span>
            <span className="chapter-item">
              <input
                className="field"
                value={titles[k]}
                aria-label={`Titre de la notion ${chapter.number}.${k + 1}`}
                onChange={(event) =>
                  setTitles(titles.map((title, j) => (j === k ? event.target.value : title)))
                }
              />
              <span className="hint">
                {notion.summary} ·{' '}
                {pagesOf(
                  files.find((file) => file.id === notion.resource_id),
                  notion.first_page,
                  notion.last_page,
                  several,
                )}
              </span>
            </span>
          </li>
        ))}
      </ol>
      {error && <Notice>{error}</Notice>}
      <div className="actions">
        <button type="submit" className="button primary" disabled={!ready}>
          Valider les notions
        </button>
      </div>
    </form>
  )
}
