import { useEffect, useState } from 'react'
import { Link } from 'react-router'
import { listSubjects, messageOf, type SubjectSummary } from '../../api.ts'
import { Icon } from '../../components/Icon.tsx'
import { Notice } from '../../components/Notice.tsx'
import { PageHeader } from '../../components/PageHeader.tsx'
import { count, shortDate } from '../../format.ts'
import './SubjectsScreen.css'

/** Mes matières: the active subjects, the closest exam first. */
export function SubjectsScreen() {
  const [subjects, setSubjects] = useState<SubjectSummary[]>()
  const [error, setError] = useState<string>()

  useEffect(() => {
    listSubjects().then(setSubjects, (reason: unknown) => setError(messageOf(reason)))
  }, [])

  return (
    <>
      <PageHeader
        label="Cours"
        title="Mes matières"
        action={
          <Link to="/matieres/nouvelle" className="button primary">
            <Icon name="plus" size={16} />
            Nouvelle matière
          </Link>
        }
      />
      {error && <Notice>{error}</Notice>}
      {subjects?.length === 0 && (
        <p className="card subjects-empty">
          Aucune matière pour l'instant. Crée la première avec « Nouvelle matière » : tu
          y importes tes livres et tes notes, et l'IA propose objectifs et chapitres.
        </p>
      )}
      {subjects && subjects.length > 0 && (
        <div className="subjects-grid">
          {subjects.map((subject) => (
            <Link key={subject.id} to={`/matieres/${subject.id}`} className="card subject-card">
              <span className="subject-card-name">{subject.name}</span>
              <span className="subject-card-exam">
                Examen final le {shortDate(subject.exam_date)}
              </span>
              <span className="subject-card-facts">
                <span>
                  {subject.chapter_count > 0
                    ? count(subject.chapter_count, 'chapitre')
                    : 'Découpage en attente'}
                </span>
                <span>{count(subject.resource_count, 'document')}</span>
              </span>
            </Link>
          ))}
        </div>
      )}
    </>
  )
}
