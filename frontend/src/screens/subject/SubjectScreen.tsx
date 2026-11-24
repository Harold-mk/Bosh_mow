import { useEffect, useState } from 'react'
import { useParams } from 'react-router'
import { getSubject, messageOf, type Subject } from '../../api.ts'
import { Icon } from '../../components/Icon.tsx'
import { KeyFigure } from '../../components/KeyFigure.tsx'
import { Notice } from '../../components/Notice.tsx'
import { PageHeader } from '../../components/PageHeader.tsx'
import { daysUntil, fileSummary, longDate } from '../../format.ts'
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
                <li key={k}>
                  <span className="mono subject-number">{k + 1}</span>
                  <span className="subject-item">
                    <span className="subject-item-title">{chapter.title}</span>
                    <span className="hint">{chapter.role === 'core' ? 'Cœur' : 'Secondaire'}</span>
                  </span>
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
                <li key={resource.id}>
                  <Icon name="file" />
                  <span className="subject-item">
                    <span className="subject-item-title">{resource.file_name}</span>
                    <span className="hint">{fileSummary(resource)}</span>
                  </span>
                </li>
              ))}
            </ul>
          </section>
        </div>
      </div>
    </>
  )
}
