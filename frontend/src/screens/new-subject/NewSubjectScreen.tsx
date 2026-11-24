import { useEffect, useState } from 'react'
import { Link } from 'react-router'
import {
  askProposal,
  createSubject,
  getDraft,
  getProposal,
  messageOf,
  updateDraft,
  type Subject,
} from '../../api.ts'
import { Icon } from '../../components/Icon.tsx'
import { Notice } from '../../components/Notice.tsx'
import { PageHeader } from '../../components/PageHeader.tsx'
import { count, longDate } from '../../format.ts'
import { filesKey, splitsFiles } from '../../useProposal.ts'
import { FilesStep } from './FilesStep.tsx'
import { ProposalStep } from './ProposalStep.tsx'
import './NewSubjectScreen.css'

const STEPS = ['Infos', 'Documents', "Proposition de l'IA"]

/** Nouvelle matière (S1): name and exam date, files, then Claude's proposal to correct.
 *  The subject is a draft until then; a draft left here is taken up again. */
export function NewSubjectScreen() {
  const [draft, setDraft] = useState<Subject | null>() // undefined while looking for one
  const [step, setStep] = useState(0)
  const [askedFor, setAskedFor] = useState('') // the files of the last proposal asked for
  const [created, setCreated] = useState<Subject>()
  const [error, setError] = useState<string>()

  // Take up the draft left here, at the step where it was left.
  useEffect(() => {
    async function takeUp() {
      const found = await getDraft()
      if (found && found.resources.length > 0) {
        const state = await getProposal(found.id)
        const outdated = state?.proposal && !splitsFiles(state.proposal, found.resources)
        if (state && !outdated) {
          setAskedFor(filesKey(found.resources))
          setStep(2)
        } else {
          setStep(1)
        }
      } else if (found) {
        setStep(1)
      }
      setDraft(found)
    }
    takeUp().catch((reason: unknown) => setError(messageOf(reason)))
  }, [])

  /** Ask Claude for a proposal, unless one was asked for these very files. */
  async function showProposal(current: Subject) {
    const key = filesKey(current.resources)
    setError(undefined)
    try {
      if (key !== askedFor) {
        await askProposal(current.id)
        setAskedFor(key)
      }
      setStep(2)
    } catch (reason) {
      setError(messageOf(reason))
    }
  }

  const header = (
    <PageHeader parents={[{ label: 'Mes matières', to: '/matieres' }]} title="Nouvelle matière" />
  )
  if (draft === undefined) {
    return (
      <>
        {header}
        {error && <Notice>{error}</Notice>}
      </>
    )
  }

  return (
    <>
      {header}
      <section className="card wizard">
        <ol className="stepper" aria-label="Étapes">
          {STEPS.map((name, k) => {
            const done = created !== undefined || k < step
            const current = created === undefined && k === step
            return (
              <li
                key={name}
                className={done ? 'done' : current ? 'current' : undefined}
                aria-current={current ? 'step' : undefined}
              >
                <span className="stepper-number">{done ? '✓' : k + 1}</span>
                {name}
              </li>
            )
          })}
        </ol>

        {created ? (
          <Created subject={created} />
        ) : step === 0 ? (
          <InfoStep
            draft={draft}
            onSaved={(saved) => {
              setDraft(saved)
              setStep(1)
            }}
          />
        ) : step === 1 && draft ? (
          <FilesStep
            subjectId={draft.id}
            files={draft.resources}
            onAdded={(file) =>
              setDraft((current) => current && { ...current, resources: [...current.resources, file] })
            }
            onRemoved={(fileId) =>
              setDraft(
                (current) =>
                  current && {
                    ...current,
                    resources: current.resources.filter((file) => file.id !== fileId),
                  },
              )
            }
            onNext={() => showProposal(draft)}
            onBack={() => setStep(0)}
          />
        ) : draft ? (
          <ProposalStep draft={draft} onBack={() => setStep(1)} onCreated={setCreated} />
        ) : null}

        {error && <Notice>{error}</Notice>}
      </section>
    </>
  )
}

type InfoProps = { draft: Subject | null; onSaved: (subject: Subject) => void }

/** Infos: the name of the subject and the date of its final exam (R2). */
function InfoStep({ draft, onSaved }: InfoProps) {
  const [name, setName] = useState(draft?.name ?? '')
  const [examDate, setExamDate] = useState(draft?.exam_date ?? '')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string>()
  const ready = name.trim() !== '' && examDate !== ''

  async function save() {
    setSaving(true)
    setError(undefined)
    try {
      onSaved(
        draft ? await updateDraft(draft.id, name, examDate) : await createSubject(name, examDate),
      )
    } catch (reason) {
      setError(messageOf(reason))
      setSaving(false)
    }
  }

  return (
    <div className="wizard-step">
      <div className="wizard-fields">
        <div className="wizard-field wizard-name">
          <label className="label" htmlFor="subject-name">
            Nom de la matière
          </label>
          <input
            id="subject-name"
            className="field"
            type="text"
            placeholder="Par exemple : Économétrie"
            value={name}
            onChange={(event) => setName(event.target.value)}
          />
        </div>
        <div className="wizard-field wizard-date">
          <label className="label" htmlFor="subject-exam">
            Date de l'examen final
          </label>
          <input
            id="subject-exam"
            className="field mono"
            type="date"
            value={examDate}
            onChange={(event) => setExamDate(event.target.value)}
          />
        </div>
      </div>
      {error && <Notice>{error}</Notice>}
      <div className="actions wizard-actions">
        <button
          type="button"
          className="button primary"
          disabled={!ready || saving}
          onClick={save}
        >
          Continuer
        </button>
        <span className="hint">
          {ready
            ? 'Tout est prêt.'
            : "Il faut un nom et une date d'examen. Les objectifs viendront de tes documents."}
        </span>
      </div>
    </div>
  )
}

/** The subject is created: what it holds, and where to go next. */
function Created({ subject }: { subject: Subject }) {
  const objectives = count(subject.objectives.length, 'objectif')
  const exam = `pour un examen final le ${longDate(subject.exam_date)}`
  return (
    <div className="wizard-created">
      <span className="wizard-check">
        <Icon name="check" />
      </span>
      <h2>{subject.name} est prête</h2>
      <p>
        {subject.chapters.length > 0
          ? `${objectives} et ${count(subject.chapters.length, 'chapitre')}, ${exam}.`
          : `${objectives}, ${exam}. Claude proposera le découpage en chapitres dès qu'il sera disponible : tu le valideras sur la page de la matière.`}
      </p>
      <div className="actions">
        <Link to="/matieres" className="button primary">
          Retour à mes matières
        </Link>
        <Link to={`/matieres/${subject.id}`} className="button ghost">
          Voir la matière
        </Link>
      </div>
    </div>
  )
}
