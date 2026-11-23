import { useEffect, useState } from 'react'

/** Response of GET /api/health. */
type Health = { status: string; version: string }

type HealthState =
  | { kind: 'loading' }
  | { kind: 'ok'; health: Health }
  | { kind: 'error'; message: string }

function App() {
  const [state, setState] = useState<HealthState>({ kind: 'loading' })

  useEffect(() => {
    fetch('/api/health')
      .then((response) => {
        if (!response.ok) throw new Error(`HTTP ${response.status}`)
        return response.json() as Promise<Health>
      })
      .then((health) => setState({ kind: 'ok', health }))
      .catch((error: unknown) => setState({ kind: 'error', message: String(error) }))
  }, [])

  return (
    <main>
      <h1>BOSH MOW</h1>
      {state.kind === 'loading' && <p>Connexion au serveur…</p>}
      {state.kind === 'ok' && (
        <p>
          Serveur : {state.health.status} — version{' '}
          <span className="mono">{state.health.version}</span>
        </p>
      )}
      {state.kind === 'error' && <p>Serveur injoignable ({state.message})</p>}
    </main>
  )
}

export default App
