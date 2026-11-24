import { validateSubject, type Resource, type Subject } from '../../api.ts'
import { Notice } from '../../components/Notice.tsx'
import { ProposalForm } from '../../components/ProposalForm.tsx'
import { useProposal } from '../../useProposal.ts'

type Props = {
  subjectId: number
  files: Resource[]
  onValidated: (subject: Subject) => void
}

/** The split into chapters of a subject created with handwritten objectives (R2):
 *  where Claude's proposal stands, then the proposal to correct and validate. */
export function PendingSplit({ subjectId, files, onValidated }: Props) {
  const { state, error, ask } = useProposal(subjectId)

  const askButton = (label: string) => (
    <button type="button" className="button secondary" onClick={ask}>
      {label}
    </button>
  )

  if (error) {
    return (
      <div className="pending-split">
        <Notice>{error}</Notice>
        {askButton('Redemander une proposition')}
      </div>
    )
  }
  if (state === undefined) return null
  if (state === null) {
    return (
      <div className="pending-split">
        <p>Aucun découpage n'a encore été demandé à Claude.</p>
        {askButton('Demander le découpage')}
      </div>
    )
  }
  if (state.status === 'done' && state.proposal) {
    return (
      <ProposalForm
        initial={state.proposal}
        files={files}
        intro="La proposition de Claude est prête. Ses objectifs remplacent ceux que tu as écrits en attendant : relis-les et corrige-les avant de valider."
        submitLabel="Valider le découpage"
        onSubmit={async (proposal) => onValidated(await validateSubject(subjectId, proposal))}
      />
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
