import { useState } from 'react'
import { useNavigate } from 'react-router'
import { messageOf, saveSettings, type Settings } from '../../api.ts'
import { Logo, Wordmark } from '../../components/Brand.tsx'
import { Notice } from '../../components/Notice.tsx'
import { Segmented } from '../../components/Segmented.tsx'
import { duration } from '../../format.ts'
import './WelcomeScreen.css'

const IDEAS = [
  {
    title: 'Te tester plutôt que relire',
    text: "Chercher une réponse de mémoire fixe le souvenir bien mieux qu'une relecture.",
  },
  {
    title: 'Revoir au bon moment',
    text: "Chaque question revient juste avant que tu l'oublies : souvent au début, puis de plus en plus espacée.",
  },
  {
    title: 'Un peu chaque jour',
    text: "Un minimum de 15 minutes, et jamais deux jours manqués d'affilée.",
  },
]
const WEEKDAY_MINUTES = [30, 60, 90, 120]
const WEEKEND_MINUTES = [60, 120, 180, 240]
const STEPS = 3

type Props = { onDone: (settings: Settings) => void }

/** Bienvenue: the first launch. Three habits, the study time per day (R11) and the
 *  plan "si… alors…" (R25), then the first subject. */
export function WelcomeScreen({ onDone }: Props) {
  const navigate = useNavigate()
  const [step, setStep] = useState(0)
  const [weekdayMinutes, setWeekdayMinutes] = useState(90)
  const [weekendMinutes, setWeekendMinutes] = useState(180)
  const [planIf, setPlanIf] = useState("je rentre et que j'ai dîné")
  const [planThen, setPlanThen] = useState('je lance la file du jour à 19 h')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string>()
  const planReady = planIf.trim() !== '' && planThen.trim() !== ''

  async function finish() {
    setSaving(true)
    setError(undefined)
    try {
      const saved = await saveSettings({
        weekday_minutes: weekdayMinutes,
        weekend_minutes: weekendMinutes,
        plan_if: planIf.trim(),
        plan_then: planThen.trim(),
        sidebar_collapsed: false,
      })
      onDone(saved)
      navigate('/matieres/nouvelle', { replace: true })
    } catch (reason) {
      setError(messageOf(reason))
      setSaving(false)
    }
  }

  const back = (
    <button type="button" className="button ghost" onClick={() => setStep(step - 1)}>
      Retour
    </button>
  )

  return (
    <div className="welcome">
      <main className="card welcome-card">
        <div className="welcome-brand">
          <Logo size={40} />
          <Wordmark height={18} />
        </div>
        <div className="welcome-steps" aria-hidden="true">
          {Array.from({ length: STEPS }, (_, k) => (
            <span
              key={k}
              className={[k <= step && 'reached', k === step && 'current']
                .filter(Boolean)
                .join(' ')}
            />
          ))}
        </div>

        {step === 0 && (
          <div className="welcome-step">
            <h1>Bienvenue, bosh mow</h1>
            <p>
              Bosh mow t'aide à apprendre pour de bon, pas à relire. Tout repose sur trois
              habitudes, prouvées par la recherche.
            </p>
            <ol className="welcome-ideas">
              {IDEAS.map((idea, k) => (
                <li key={idea.title}>
                  <span className="welcome-number">{k + 1}</span>
                  <span>
                    <strong>{idea.title}</strong>
                    <span className="welcome-idea">{idea.text}</span>
                  </span>
                </li>
              ))}
            </ol>
            <div className="actions">
              <button type="button" className="button primary" onClick={() => setStep(1)}>
                Commencer
              </button>
            </div>
          </div>
        )}

        {step === 1 && (
          <div className="welcome-step">
            <h1>Quand vas-tu travailler ?</h1>
            <p>
              Mieux vaut un peu chaque jour que beaucoup une fois par semaine. Tu pourras
              tout changer plus tard dans le planning.
            </p>
            <div className="welcome-question">
              <span className="welcome-question-title">En semaine, chaque jour</span>
              <Segmented
                label="Temps en semaine"
                mono
                options={WEEKDAY_MINUTES.map((m) => ({ value: m, label: duration(m) }))}
                value={weekdayMinutes}
                onChange={setWeekdayMinutes}
              />
            </div>
            <div className="welcome-question">
              <span className="welcome-question-title">Le week-end, chaque jour</span>
              <Segmented
                label="Temps le week-end"
                mono
                options={WEEKEND_MINUTES.map((m) => ({ value: m, label: duration(m) }))}
                value={weekendMinutes}
                onChange={setWeekendMinutes}
              />
            </div>
            <div className="welcome-question">
              <span className="welcome-question-title">Ton plan « si… alors… »</span>
              <div className="welcome-plan">
                <label htmlFor="plan-if">Si</label>
                <input
                  id="plan-if"
                  className="field"
                  type="text"
                  value={planIf}
                  onChange={(event) => setPlanIf(event.target.value)}
                />
                <label htmlFor="plan-then">alors</label>
                <input
                  id="plan-then"
                  className="field"
                  type="text"
                  value={planThen}
                  onChange={(event) => setPlanThen(event.target.value)}
                />
              </div>
              <span className="hint">
                Lier ton travail à un moment précis de ta journée double tes chances de t'y
                tenir.
              </span>
            </div>
            <span>
              Soit{' '}
              <span className="mono welcome-total">
                {duration(weekdayMinutes * 5 + weekendMinutes * 2)}
              </span>{' '}
              par semaine.
            </span>
            <div className="actions">
              <button
                type="button"
                className="button primary"
                disabled={!planReady}
                onClick={() => setStep(2)}
              >
                Continuer
              </button>
              {back}
              {!planReady && <span className="hint">Complète ton plan « si… alors… ».</span>}
            </div>
          </div>
        )}

        {step === 2 && (
          <div className="welcome-step">
            <h1>Ta première matière</h1>
            <p>
              Donne-lui un nom et une date d'examen, puis ajoute tes livres en PDF et tes
              notes en Markdown. L'IA proposera tes objectifs et un découpage en chapitres,
              que tu relis avant de valider.
            </p>
            <div className="welcome-summary">
              Ton planning :{' '}
              <strong>
                {duration(weekdayMinutes)} en semaine, {duration(weekendMinutes)} le
                week-end
              </strong>
              . Le premier soir, tu commences par 15 minutes seulement.
            </div>
            <div className="actions">
              <button
                type="button"
                className="button primary"
                disabled={saving}
                onClick={finish}
              >
                Créer ma première matière
              </button>
              {back}
            </div>
            {error && <Notice>{error}</Notice>}
          </div>
        )}
      </main>
    </div>
  )
}
