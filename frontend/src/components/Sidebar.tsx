import { NavLink } from 'react-router'
import { Logo, Wordmark } from './Brand.tsx'
import { Icon } from './Icon.tsx'
import './Sidebar.css'

type Props = { collapsed: boolean; onToggle: () => void }

/** The main menu. It lists only the screens that exist: Cours for now, the other
 *  entries and the "Minimum du jour" card come with their screens. */
export function Sidebar({ collapsed, onToggle }: Props) {
  const toggle = collapsed ? 'Afficher le menu' : 'Réduire le menu'
  return (
    <nav aria-label="Menu principal" className={collapsed ? 'sidebar collapsed' : 'sidebar'}>
      <div className="sidebar-brand">
        <Logo size={32} />
        {!collapsed && <Wordmark height={15} />}
        <button
          type="button"
          className="sidebar-toggle"
          aria-label={toggle}
          title={toggle}
          onClick={onToggle}
        >
          <Icon name={collapsed ? 'expand' : 'collapse'} />
        </button>
      </div>
      <NavLink
        to="/matieres"
        className="sidebar-link"
        title={collapsed ? 'Cours' : undefined}
        aria-label={collapsed ? 'Cours' : undefined}
      >
        <Icon name="course" />
        {!collapsed && 'Cours'}
      </NavLink>
    </nav>
  )
}
