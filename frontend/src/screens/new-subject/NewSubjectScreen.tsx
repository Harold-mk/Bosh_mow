import { PageHeader } from '../../components/PageHeader.tsx'

/** Nouvelle matière: name and exam date, files, then the proposal of Claude. */
export function NewSubjectScreen() {
  return <PageHeader parents={[{ label: 'Mes matières', to: '/matieres' }]} title="Nouvelle matière" />
}
