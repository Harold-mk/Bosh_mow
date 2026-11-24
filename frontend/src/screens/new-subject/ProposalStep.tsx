import { useEffect, useState } from 'react'
import { validateSubject, type Proposal, type Subject } from '../../api.ts'
import { Notice } from '../../components/Notice.tsx'
import { ProposalForm } from '../../components/ProposalForm.tsx'
import { count } from '../../format.ts'
import { splitsFiles, useProposal } from '../../useProposal.ts'

const BY_HAND: Proposal = { objectives: [''], chapters: [], glossary: [] }

type Props = {
  draft: Subject
  onBack: () => void
  onCreated: (subject: Subject) => void
}

/** Proposition de l'IA: Claude's objectives and chapters, to correct then validate.
 *  Without Claude, the objectives can be written by hand in the meantime (R2). */
export function ProposalStep({ draft, onBack, onCreated }: Props) {
  const { state, error, ask } = useProposal(draft.id)
  const [byHand, setByHand] = useState(false)

  // The files changed while Claude was working: his proposal is for the old ones.
  const outdated =
    state?.status === 'done' &&
    state.proposal !== null &&
    !splitsFiles(state.proposal, draft.resources)
  useEffect(() => {
    if (outdated) ask()
  }, [outdated, ask])

  async function create(proposal: Proposal) {
    onCreated(await validateSubject(draft.id, proposal))
  }

  const back = (
    <button type="button" className="button ghost" onClick={onBack}>
      Retour
    </button>
  )
  const writeByHand = (
    <button type="button" className="button ghost" onClick={() => setByHand(true)}>
      Écrire mes objectifs moi-même
    </button>
  )

  if (byHand) {
    return (
      <ProposalForm
        initial={BY_HAND}
        files={draft.resources}
        intro="Écris tes objectifs, 5 au plus. Claude proposera le découpage en chapitres dès qu'il sera disponible : tu le valideras sur la page de la matière."
        submitLabel="Créer la matière"
        onSubmit={create}
      >
        <button type="button" className="button ghost" onClick={() => setByHand(false)}>
          Retour
        </button>
      </ProposalForm>
    )
  }
  if (error) {
    return (
      <div className="wizard-step">
        <Notice>{error}</Notice>
        <div className="actions">
          <button type="button" className="button secondary" onClick={ask}>
            Redemander une proposition
          </button>
          {back}
        </div>
      </div>
    )
  }
  if (state === undefined) return null
  if (state?.status === 'done' && state.proposal && !outdated) {
    const { objectives, chapters } = state.proposal
    return (
      <ProposalForm
        initial={state.proposal}
        files={draft.resources}
        intro={
          <>
            L'IA a analysé tes fichiers et propose{' '}
            <strong>
              {count(objectives.length, 'objectif')} et un découpage en{' '}
              {count(chapters.length, 'chapitre')}
            </strong>
            . Relis-les et corrige-les avant de valider.
          </>
        }
        submitLabel="Créer la matière"
        onSubmit={create}
      >
        {back}
      </ProposalForm>
    )
  }
  if (state === null) {
    return (
      <div className="wizard-step">
        <p>Aucune proposition n'a encore été demandée à Claude.</p>
        <div className="actions">
          <button type="button" className="button secondary" onClick={ask}>
            Demander une proposition
          </button>
          {back}
        </div>
      </div>
    )
  }
  if (state.status === 'failed') {
    return (
      <div className="wizard-step">
        <p>La proposition de Claude n'a pas passé les contrôles.</p>
        <span className="hint">Détail : {state.error}</span>
        <div className="actions">
          <button type="button" className="button secondary" onClick={ask}>
            Redemander une proposition
          </button>
          {writeByHand}
          {back}
        </div>
      </div>
    )
  }
  if (state.status === 'pending' && state.error) {
    return (
      <div className="wizard-step">
        <p>
          Claude n'est pas disponible pour l'instant : {state.error} Bosh mow réessaiera
          tout seul dans quelques minutes. En attendant, tu peux écrire tes objectifs
          toi-même et créer la matière.
        </p>
        <div className="actions">
          <button type="button" className="button secondary" onClick={ask}>
            Réessayer maintenant
          </button>
          {writeByHand}
          {back}
        </div>
      </div>
    )
  }
  return (
    <div className="wizard-step">
      <div className="wizard-wait">
        <span className="analysis-dots" aria-hidden="true">
          {Array.from({ length: 10 }, (_, k) => (
            <span key={k} />
          ))}
        </span>
        <p>
          L'IA lit tes documents et prépare tes objectifs et tes chapitres. Cela prend en
          général moins d'une minute ; tu peux aussi quitter cette page et revenir plus tard.
        </p>
      </div>
      <div className="actions">{back}</div>
    </div>
  )
}
