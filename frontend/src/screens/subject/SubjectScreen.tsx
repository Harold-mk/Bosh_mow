import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router'
import {
  type ChapterSummary,
  getDescriptions,
  getSubject,
  listChapters,
  messageOf,
  type DescriptionCount,
  type Subject,
} from '../../api.ts'
import { Icon } from '../../components/Icon.tsx'
import { KeyFigure } from '../../components/KeyFigure.tsx'
import { Notice } from '../../components/Notice.tsx'
import { PageHeader } from '../../components/PageHeader.tsx'
import { count, daysUntil, fileSummary, longDate } from '../../format.ts'
import { PendingSplit } from './PendingSplit.tsx'
import './SubjectScreen.css'

const PARENTS = [{ label: 'Mes matières', to: '/matieres' }]

/** Matière: the page of one subject. Only what exists in lot 1 is shown: mastery,
 *  reviews, time and evaluations come with their lots. */
export function SubjectScreen() {
  const subjectId = Number(useParams().subjectId)
  const [subject, setSubject] = useState<Subject>()
  const [error, setError] = useState<string>()

  useEffect(() => {
    getSubject(subjectId).then(setSubject, (reason: unknown) => setError(messageOf(reason)))
  }, [subjectId])

  // The pages mostly in images are described once the chapters are validated (T11).
  const [descriptions, setDescriptions] = useState<DescriptionCount[]>([])
  const split = (subject?.chapters.length ?? 0) > 0
  useEffect(() => {
    if (!split) return
    // Only a progress line: if it cannot be read, the page shows no line.
    getDescriptions(subjectId).then(setDescriptions, () => {})
  }, [subjectId, split])

  // Where the notions of each chapter stand: proposed, validated, studied.
  const [summaries, setSummaries] = useState<ChapterSummary[]>([])
  useEffect(() => {
    if (!split) return
    // Only progress lines: if they cannot be read, the rows show none.
    listChapters(subjectId).then(setSummaries, () => {})
  }, [subjectId, split])

  if (error) {
    return (
      <>
        <PageHeader parents={PARENTS} title="Matière" />
        <Notice>{error}</Notice>
      </>
    )
  }
  if (!subject) return null

  const days = daysUntil(subject.exam_date)
  const examDate = `Le ${longDate(subject.exam_date)}`
  return (
    <>
      <PageHeader parents={PARENTS} title={subject.name} />
      <div className="key-figures">
        <KeyFigure
          label="Examen final"
          value={Math.max(days, 0)}
          unit={days < 2 ? 'jour' : 'jours'}
          context={days < 0 ? `${examDate}, déjà passé` : examDate}
        />
      </div>
      <div className="subject-columns">
        <section className="card subject-chapters">
          <h2>Chapitres</h2>
          {subject.chapters.length > 0 ? (
            <ol className="subject-list">
              {subject.chapters.map((chapter, k) => (
                <li key={k} className="subject-link">
                  <Link to={`/matieres/${subject.id}/chapitres/${k + 1}`} className="subject-row">
                    <span className="mono subject-number">{k + 1}</span>
                    <span className="subject-item">
                      <span className="subject-item-title">{chapter.title}</span>
                      <span className="hint">
                        {[chapter.role === 'core' ? 'Cœur' : 'Secondaire', notionsText(summaries[k])]
                          .filter(Boolean)
                          .join(' · ')}
                      </span>
                    </span>
                  </Link>
                </li>
              ))}
            </ol>
          ) : (
            <PendingSplit
              subjectId={subject.id}
              files={subject.resources}
              onValidated={setSubject}
            />
          )}
        </section>
        <div className="subject-side">
          <section className="card subject-section">
            <h2>Objectifs</h2>
            <ol className="subject-list">
              {subject.objectives.map((objective, k) => (
                <li key={k}>
                  <span className="mono subject-number">{k + 1}</span>
                  <span className="subject-objective">{objective}</span>
                </li>
              ))}
            </ol>
          </section>
          <section className="card subject-section">
            <h2>Documents</h2>
            <ul className="subject-files">
              {subject.resources.map((resource) => (
                <li key={resource.id} className="subject-link">
                  <Link to={`/lecteur/${resource.id}`} className="subject-file">
                  <Icon name="file" />
                  <span className="subject-item">
                    <span className="subject-item-title">{resource.file_name}</span>
                    <span className="hint">{fileSummary(resource)}</span>
                    {descriptions
                      .filter((progress) => progress.resource_id === resource.id)
                      .map((progress) => (
                        <span key={progress.resource_id} className="hint">
                          {describedText(progress)}
                        </span>
                      ))}
                  </span>
                  </Link>
                </li>
              ))}
            </ul>
          </section>
        </div>
      </div>
    </>
  )
}

/** Where the notions of a chapter stand, in a few words; '' before they are asked. */
function notionsText(summary: ChapterSummary | undefined): string {
  if (!summary) return ''
  if (summary.notions > 0) return `Notions étudiées : ${summary.studied} / ${summary.notions}`
  switch (summary.preparation) {
    case 'done':
      return 'Notions proposées, à valider'
    case 'pending':
    case 'running':
      return 'Notions en préparation'
    case 'failed':
      return 'Notions à redemander'
    default:
      return ''
  }
}

/** "12 pages de schémas décrites sur 26", or "26 pages de schémas décrites". */
function describedText({ to_describe, described }: DescriptionCount): string {
  const done = described < 2 ? 'décrite' : 'décrites'
  if (described === to_describe) return `${count(to_describe, 'page')} de schémas ${done}`
  return `${count(described, 'page')} de schémas ${done} sur ${to_describe}`
}
