import { useEffect, useState } from 'react'
import { HashRouter, Navigate, Route, Routes } from 'react-router'
import { getSettings, messageOf, type Settings } from './api.ts'
import { Layout } from './components/Layout.tsx'
import { Notice } from './components/Notice.tsx'
import { HomeScreen } from './screens/home/HomeScreen.tsx'
import { NewSubjectScreen } from './screens/new-subject/NewSubjectScreen.tsx'
import { NotionScreen } from './screens/notion/NotionScreen.tsx'
import { SessionScreen } from './screens/session/SessionScreen.tsx'
import { SubjectScreen } from './screens/subject/SubjectScreen.tsx'
import { SubjectsScreen } from './screens/subjects/SubjectsScreen.tsx'
import { WelcomeScreen } from './screens/welcome/WelcomeScreen.tsx'

/** The settings are read once, at start: without them, the first launch is not done. */
type Start =
  | { kind: 'loading' }
  | { kind: 'ready'; settings: Settings | null }
  | { kind: 'error'; message: string }

/** The screens and their addresses. Bienvenue comes first, until the settings exist. */
export function App() {
  const [start, setStart] = useState<Start>({ kind: 'loading' })

  useEffect(() => {
    getSettings().then(
      (settings) => setStart({ kind: 'ready', settings }),
      (reason: unknown) => setStart({ kind: 'error', message: messageOf(reason) }),
    )
  }, [])

  if (start.kind === 'loading') return null
  if (start.kind === 'error') {
    return (
      <div className="app">
        <Notice>{start.message}</Notice>
      </div>
    )
  }
  const { settings } = start
  const setSettings = (changed: Settings) => setStart({ kind: 'ready', settings: changed })

  return (
    <HashRouter>
      <Routes>
        {/* Only reached without settings: Bienvenue itself leads on to the first subject. */}
        <Route path="/bienvenue" element={<WelcomeScreen onDone={setSettings} />} />
        {/* A session takes the whole window, without the sidebar (R16). */}
        <Route
          path="/session"
          element={settings ? <SessionScreen /> : <Navigate to="/bienvenue" replace />}
        />
        <Route
          element={
            settings ? (
              <Layout settings={settings} onSettingsChange={setSettings} />
            ) : (
              <Navigate to="/bienvenue" replace />
            )
          }
        >
          <Route path="/accueil" element={<HomeScreen />} />
          <Route path="/notion" element={<NotionScreen />} />
          <Route path="/matieres" element={<SubjectsScreen />} />
          <Route path="/matieres/nouvelle" element={<NewSubjectScreen />} />
          <Route path="/matieres/:subjectId" element={<SubjectScreen />} />
        </Route>
        <Route path="*" element={<Navigate to="/accueil" replace />} />
      </Routes>
    </HashRouter>
  )
}
