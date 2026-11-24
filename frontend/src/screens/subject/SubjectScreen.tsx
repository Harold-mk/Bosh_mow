import { useEffect, useState } from 'react'
import { useParams } from 'react-router'
import { getSubject, messageOf, type Subject } from '../../api.ts'
import { Notice } from '../../components/Notice.tsx'
import { PageHeader } from '../../components/PageHeader.tsx'

const PARENTS = [{ label: 'Mes matières', to: '/matieres' }]

/** Matière: the page of one subject. */
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
  return <PageHeader parents={PARENTS} title={subject.name} />
}
