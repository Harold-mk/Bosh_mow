import { Link } from 'react-router'
import { Icon } from '../../components/Icon.tsx'
import { PageHeader } from '../../components/PageHeader.tsx'

/** Mes matières: the active subjects, the closest exam first. */
export function SubjectsScreen() {
  return (
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
  )
}
