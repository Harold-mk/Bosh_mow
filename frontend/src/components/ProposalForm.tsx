import { useRef, useState, type ReactNode } from 'react'
import { messageOf, type Chapter, type Proposal, type Resource, type Role } from '../api.ts'
import { count } from '../format.ts'
import { Icon } from './Icon.tsx'
import { Notice } from './Notice.tsx'
import { Segmented } from './Segmented.tsx'
import './ProposalForm.css'

const MAX_OBJECTIVES = 5 // R2
const ROLES: { value: Role; label: string }[] = [
  { value: 'core', label: 'Cœur' },
  { value: 'secondary', label: 'Secondaire' },
]

type Props = {
  initial: Proposal
  files: Resource[] // the files of the subject, to say where each chapter is
  intro: ReactNode
  submitLabel: string
  onSubmit: (proposal: Proposal) => Promise<void>
  children?: ReactNode // more buttons, after the submit button
}

/** Objectives and chapters to correct before they are saved (R2, R3). Objectives can
 *  be edited, added or removed; a chapter keeps its pages, its title can change, and
 *  it is marked core or secondary. */
export function ProposalForm({ initial, files, intro, submitLabel, onSubmit, children }: Props) {
  // Each objective keeps its key when another one is removed, and so its input.
  const [objectives, setObjectives] = useState(() =>
    initial.objectives.map((text, key) => ({ key, text })),
  )
  const nextKey = useRef(initial.objectives.length)
  const [chapters, setChapters] = useState(initial.chapters)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string>()

  const problem =
    objectives.length === 0
      ? 'Il faut au moins un objectif.'
      : objectives.some((objective) => !objective.text.trim())
        ? 'Remplis ou retire les objectifs vides.'
        : chapters.some((chapter) => !chapter.title.trim())
          ? "Chaque chapitre a besoin d'un titre."
          : undefined
  const coreCount = chapters.filter((chapter) => chapter.role === 'core').length

  function addObjective() {
    setObjectives([...objectives, { key: nextKey.current++, text: '' }])
  }

  function editObjective(index: number, text: string) {
    setObjectives(objectives.map((objective, k) => (k === index ? { ...objective, text } : objective)))
  }

  /** Remove an objective: the chapters keep their links to the others, renumbered. */
  function removeObjective(index: number) {
    const removed = index + 1
    setObjectives(objectives.filter((_, k) => k !== index))
    setChapters(
      chapters.map((chapter) => ({
        ...chapter,
        objectives: chapter.objectives
          .filter((n) => n !== removed)
          .map((n) => (n > removed ? n - 1 : n)),
      })),
    )
  }

  function editChapter(index: number, change: Partial<Chapter>) {
    setChapters(chapters.map((chapter, k) => (k === index ? { ...chapter, ...change } : chapter)))
  }

  async function submit() {
    setSaving(true)
    setError(undefined)
    try {
      await onSubmit({
        objectives: objectives.map((objective) => objective.text.trim()),
        chapters: chapters.map((chapter) => ({ ...chapter, title: chapter.title.trim() })),
        glossary: initial.glossary,
      })
    } catch (reason) {
      setError(messageOf(reason))
      setSaving(false)
    }
  }

  return (
    <div className="proposal">
      <div className="proposal-intro">
        <Icon name="spark" />
        <span>{intro}</span>
      </div>

      <div className="proposal-objectives">
        <span className="label">
          {chapters.length > 0 ? 'Objectifs proposés' : 'Tes objectifs'} · {MAX_OBJECTIVES} au
          plus
        </span>
        {objectives.map((objective, k) => (
          <div className="proposal-objective" key={objective.key}>
            <span className="mono proposal-number">{k + 1}</span>
            <input
              className="field"
              type="text"
              placeholder="Être capable de…"
              aria-label={`Objectif ${k + 1}`}
              value={objective.text}
              onChange={(event) => editObjective(k, event.target.value)}
            />
            <button
              type="button"
              className="icon-button"
              aria-label={`Retirer l'objectif ${k + 1}`}
              title="Retirer"
              onClick={() => removeObjective(k)}
            >
              <Icon name="close" />
            </button>
          </div>
        ))}
        {objectives.length < MAX_OBJECTIVES && (
          <button type="button" className="button ghost proposal-add" onClick={addObjective}>
            <Icon name="plus" size={16} />
            Ajouter un objectif
          </button>
        )}
      </div>

      {chapters.length > 0 && (
        <div className="proposal-chapters">
          <span className="label">
            Chapitres proposés · {count(chapters.length, 'chapitre')}, dont {coreCount} au cœur
            de la matière
          </span>
          <ol>
            {chapters.map((chapter, k) => (
              <li key={k}>
                <span className="mono proposal-number">{k + 1}</span>
                <span className="proposal-chapter">
                  <input
                    className="proposal-title"
                    type="text"
                    aria-label={`Titre du chapitre ${k + 1}`}
                    value={chapter.title}
                    onChange={(event) => editChapter(k, { title: event.target.value })}
                  />
                  <span className="hint proposal-pages">{whereIs(chapter, files)}</span>
                </span>
                <span className="proposal-tags">
                  {chapter.objectives.map((n) => (
                    <span key={n} className="proposal-tag" title={objectives[n - 1]?.text}>
                      Objectif {n}
                    </span>
                  ))}
                </span>
                <Segmented
                  small
                  label={`Importance du chapitre ${k + 1}`}
                  options={ROLES}
                  value={chapter.role}
                  onChange={(role) => editChapter(k, { role })}
                />
              </li>
            ))}
          </ol>
        </div>
      )}

      <div className="actions">
        <button
          type="button"
          className="button primary"
          disabled={problem !== undefined || saving}
          onClick={submit}
        >
          {submitLabel}
        </button>
        {children}
        {problem && <span className="hint">{problem}</span>}
      </div>
      {error && <Notice>{error}</Notice>}
    </div>
  )
}

/** Where a chapter is: "p. 12–58", "sections 1–3", with the file when there are several. */
function whereIs(chapter: Chapter, files: Resource[]): string {
  return chapter.sources
    .map((source) => {
      const file = files.find((candidate) => candidate.id === source.resource_id)
      const single = source.first_page === source.last_page
      const range = single ? `${source.first_page}` : `${source.first_page}–${source.last_page}`
      const pages =
        file?.kind === 'markdown' ? `${single ? 'section' : 'sections'} ${range}` : `p. ${range}`
      return files.length > 1 && file ? `${file.file_name}, ${pages}` : pages
    })
    .join(' · ')
}
