import { useEffect, useState } from 'react'
import { Outlet, useLocation } from 'react-router'
import { getToday, saveSettings, type Settings } from '../api.ts'
import { Sidebar } from './Sidebar.tsx'

type Props = { settings: Settings; onSettingsChange: (settings: Settings) => void }

/** The frame of every screen but Bienvenue: the sidebar, then the page. */
export function Layout({ settings, onSettingsChange }: Props) {
  const { pathname } = useLocation()
  const [minutes, setMinutes] = useState<number>()

  // The card of the day is read again on each screen: a session may have just ended.
  useEffect(() => {
    // Only a card: if the day cannot be read, the sidebar shows no card.
    getToday().then((day) => setMinutes(day.minutes), () => {})
  }, [pathname])

  function toggleSidebar() {
    const changed = { ...settings, sidebar_collapsed: !settings.sidebar_collapsed }
    onSettingsChange(changed)
    // Only a preference: if it cannot be saved, the sidebar changes all the same.
    saveSettings(changed).catch(() => {})
  }

  return (
    <div className="app">
      <Sidebar collapsed={settings.sidebar_collapsed} onToggle={toggleSidebar} minutes={minutes} />
      <main className="page">
        <Outlet />
      </main>
    </div>
  )
}
