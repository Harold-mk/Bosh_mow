import { useEffect, useState } from 'react'
import { Link } from 'react-router'
import { getToday, messageOf, type Today } from '../../api.ts'
import { Icon } from '../../components/Icon.tsx'
import { KeyFigure } from '../../components/KeyFigure.tsx'
import { Notice } from '../../components/Notice.tsx'
import { PageHeader } from '../../components/PageHeader.tsx'
import { dayLabel } from '../../format.ts'
import { queueMinutes } from '../../study.ts'

/** Accueil: the day, and the button that starts the session. Only what exists is
 *  shown: the programme of the evening, evaluations and charts come later. */
export function HomeScreen() {
  const [day, setDay] = useState<Today>()
  const [error, setError] = useState<string>()

  useEffect(() => {
    getToday().then(setDay, (reason: unknown) => setError(messageOf(reason)))
  }, [])

  const now = new Date()
  return (
    <>
      <PageHeader
        label={dayLabel(now)}
        title={now.getHours() < 18 ? 'Bonjour' : 'Bonsoir'}
        action={
          <Link to="/session" className="button primary">
            <Icon name="session" size={16} />
            {day?.after_absence ? 'Commencer la session minimum' : 'Commencer la session'}
          </Link>
        }
      />
      {error && <Notice>{error}</Notice>}
      {day && (
        <div className="key-figures">
          <KeyFigure
            label="À réviser aujourd'hui"
            value={day.due}
            unit={day.due < 2 ? 'question' : 'questions'}
            context={
              day.due > 0
                ? `environ ${queueMinutes(day.due)} minutes`
                : 'rien à réviser : place à une notion nouvelle'
            }
          />
          <KeyFigure label="Jours réussis" value={day.successful_days} context={dayContext(day)} />
        </div>
      )}
    </>
  )
}

/** One line under the successful days: never a count of days missed (R26, R27). */
function dayContext(day: Today): string {
  if (day.minimum_done) return 'Le minimum du jour est fait.'
  if (day.after_absence) return "Content de te revoir : aujourd'hui, la session minimum suffit."
  if (day.missed_yesterday) {
    return "Pas de session hier : 15 minutes aujourd'hui suffisent pour garder le rythme."
  }
  return 'Un jour est réussi dès que le minimum du jour est fait.'
}
