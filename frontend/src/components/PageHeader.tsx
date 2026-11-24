import { Fragment, type ReactNode } from 'react'
import { Link } from 'react-router'

type Props = {
  title: string
  label?: string // a word above the title, such as the menu entry ("Cours")
  parents?: { label: string; to: string }[] // the breadcrumb that leads to the page
  action?: ReactNode // the main action of the page, on the right
}

/** The top of a page: a label or a breadcrumb, the title, and the main action. */
export function PageHeader({ title, label, parents, action }: Props) {
  return (
    <header className="page-header">
      <div className="page-header-titles">
        {label && <span className="label">{label}</span>}
        {parents && (
          <nav aria-label="Fil d'Ariane" className="label breadcrumb">
            {parents.map((parent) => (
              <Fragment key={parent.to}>
                <Link to={parent.to}>{parent.label}</Link> /{' '}
              </Fragment>
            ))}
            {title}
          </nav>
        )}
        <h1>{title}</h1>
      </div>
      {action}
    </header>
  )
}
