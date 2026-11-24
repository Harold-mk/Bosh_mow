import { Logo, Wordmark } from '../../components/Brand.tsx'
import './WelcomeScreen.css'

/** Bienvenue: the first launch, before any other screen. */
export function WelcomeScreen() {
  return (
    <div className="welcome">
      <main className="card welcome-card">
        <div className="welcome-brand">
          <Logo size={40} />
          <Wordmark height={18} />
        </div>
      </main>
    </div>
  )
}
