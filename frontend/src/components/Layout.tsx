import { Outlet } from 'react-router'
import { saveSettings, type Settings } from '../api.ts'
import { Sidebar } from './Sidebar.tsx'

type Props = { settings: Settings; onSettingsChange: (settings: Settings) => void }

/** The frame of every screen but Bienvenue: the sidebar, then the page. */
export function Layout({ settings, onSettingsChange }: Props) {
  function toggleSidebar() {
    const changed = { ...settings, sidebar_collapsed: !settings.sidebar_collapsed }
    onSettingsChange(changed)
    // Only a preference: if it cannot be saved, the sidebar changes all the same.
    saveSettings(changed).catch(() => {})
  }

  return (
    <div className="app">
      <Sidebar collapsed={settings.sidebar_collapsed} onToggle={toggleSidebar} />
      <main className="page">
        <Outlet />
      </main>
    </div>
  )
}
