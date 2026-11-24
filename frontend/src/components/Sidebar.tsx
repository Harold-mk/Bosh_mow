import { Link, NavLink } from 'react-router'
import { Logo, Wordmark } from './Brand.tsx'
import { Icon, type IconName } from './Icon.tsx'
import './Sidebar.css'

const MINIMUM_MINUTES = 15 // R12
const ENTRIES: { to: string; label: string; icon: IconName }[] = [
  { to: '/accueil', label: 'Accueil', icon: 'home' },
  { to: '/session', label: 'Session', icon: 'session' },
  { to: '/matieres', label: 'Cours', icon: 'course' },
]

type Props = {
  collapsed: boolean
  onToggle: () => void
  minutes: number | undefined // studied today; undefined while unknown
}

/** The main menu, then the card of the minimum of the day. It lists only the screens
 *  that exist: the others come with their lots. */
export function Sidebar({ collapsed, onToggle, minutes }: Props) {
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
      {ENTRIES.map((entry) => (
        <NavLink
          key={entry.to}
          to={entry.to}
          className="sidebar-link"
          title={collapsed ? entry.label : undefined}
          aria-label={collapsed ? entry.label : undefined}
        >
          <Icon name={entry.icon} />
          {!collapsed && entry.label}
        </NavLink>
      ))}
      <div className="sidebar-space" />
      {minutes !== undefined && <MinimumCard minutes={minutes} collapsed={collapsed} />}
    </nav>
  )
}

/** Today's study time against the 15 minutes of the minimum session; it starts it. */
function MinimumCard({ minutes, collapsed }: { minutes: number; collapsed: boolean }) {
  const shown = Math.min(minutes, MINIMUM_MINUTES)
  if (collapsed) {
    return (
      <Link
        to="/session"
        className="minimum-card small"
        title={`Séance minimum : ${shown} sur ${MINIMUM_MINUTES} min`}
        aria-label={`Minimum du jour : ${shown} sur ${MINIMUM_MINUTES} minutes`}
      >
        <span className="mono minimum-small-value">{shown}</span>
        <span className="mono minimum-small-unit">/{MINIMUM_MINUTES}</span>
      </Link>
    )
  }
  const filled = Math.round((shown / MINIMUM_MINUTES) * 20)
  return (
    <Link to="/session" className="minimum-card">
      <span className="label">Minimum du jour</span>
      <span className="minimum-value">
        <span className="mono minimum-number">{shown}</span>
        <span className="mono minimum-unit">/ {MINIMUM_MINUTES} min</span>
      </span>
      <span className="minimum-dots" aria-hidden="true">
        {Array.from({ length: 20 }, (_, k) => (
          <span key={k} className={k < filled ? 'on' : undefined} />
        ))}
      </span>
    </Link>
  )
}
