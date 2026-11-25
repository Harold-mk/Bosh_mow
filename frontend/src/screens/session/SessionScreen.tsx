import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router'
import {
  type Confidence,
  decideThought,
  endSession,
  getNextNotion,
  getThoughts,
  getToday,
  giveAnswer,
  messageOf,
  type NotionToStudy,
  nextQuestion,
  type QuestionToAsk,
  startQueue,
  type Thought,
  type Today,
} from '../../api.ts'
import { Icon } from '../../components/Icon.tsx'
import { Notice } from '../../components/Notice.tsx'
import { count } from '../../format.ts'
import { setFullscreen } from '../../fullscreen.ts'
import { queueMinutes, SESSION_SECONDS } from '../../study.ts'
import { ReaderOverlay } from '../reader/ReaderOverlay.tsx'
import { AwayCheck } from './AwayCheck.tsx'
import { Chrono, Progress } from './Chrono.tsx'
import { FocusHeader } from './FocusHeader.tsx'
import { FocusTools } from './FocusTools.tsx'
import { type Answered, type Asked, QuestionCard } from './QuestionCard.tsx'
import './SessionScreen.css'
import { ThoughtSorting } from './ThoughtSorting.tsx'

/** The daily queue once started: its questions at the start (R26), and its clock. */
type Started = { id: number; planned: number; startedAt: number }

/** Why a session ends: its queue is empty, its time is up, or the student stops. */
type Ending = 'done' | 'time' | 'later'

type Phase =
  | { kind: 'ready' } // R16: the box to tick, then Commencer
  | { kind: 'question'; asked: Asked }
  | { kind: 'corrected'; asked: Asked; answered: Answered; next: QuestionToAsk | null }
  | { kind: 'sorting'; thoughts: Thought[]; ending: Ending } // R17, before the end
  | { kind: 'ended'; ending: Ending; rest: number; minimumDone: boolean }

/** Session: the daily queue, the minimum session (R12), in full screen and without the
 *  sidebar (R16). Its questions come one by one with their correction (T5), under a
 *  15-minute clock; thoughts are put aside (R17) and wandering is counted (R18). */
export function SessionScreen() {
  const navigate = useNavigate()
  const [day, setDay] = useState<Today>()
  const [notion, setNotion] = useState<NotionToStudy | null>(null)
  const [phase, setPhase] = useState<Phase>({ kind: 'ready' })
  const [session, setSession] = useState<Started>()
  const [answered, setAnswered] = useState<number[]>([]) // each question answered, once
  const [now, setNow] = useState(() => Date.now())
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string>()
  const [course, setCourse] = useState<QuestionToAsk>() // its pages open in the reader
  const working = useRef(false) // a call is on its way: another one is not sent

  useEffect(() => {
    Promise.all([getToday(), getNextNotion()]).then(
      ([today, next]) => {
        setDay(today)
        setNotion(next)
      },
      (reason: unknown) => setError(messageOf(reason)),
    )
    return () => setFullscreen(false) // leaving the screen leaves the full screen
  }, [])

  // The clock runs while questions are asked.
  const asking = phase.kind === 'question' || phase.kind === 'corrected'
  useEffect(() => {
    if (!asking) return
    const timer = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(timer)
  }, [asking])
  const elapsed = session ? Math.floor((now - session.startedAt) / 1000) : 0
  const left = Math.min(SESSION_SECONDS, Math.max(0, SESSION_SECONDS - elapsed))
  const timeUp = left === 0

  async function run(action: () => Promise<void>) {
    if (working.current) return
    working.current = true
    setBusy(true)
    setError(undefined)
    try {
      await action()
    } catch (reason) {
      setError(messageOf(reason))
    } finally {
      working.current = false
      setBusy(false)
    }
  }

  /** A question as shown: its place among the questions planned, or a new try (R7). */
  function toAsk(question: QuestionToAsk, planned: number): Asked {
    const number = answered.length + 1
    const label = answered.includes(question.id)
      ? `Nouvel essai · ${question.subject}`
      : `Question ${number} sur ${Math.max(planned, number)} · ${question.subject}`
    return { question, label, shownAt: Date.now() }
  }

  const start = () =>
    run(async () => {
      setFullscreen(true)
      const queue = await startQueue()
      const started = { ...queue, startedAt: Date.now() }
      setSession(started)
      setNow(started.startedAt)
      const first = await nextQuestion(started.id)
      if (first) setPhase({ kind: 'question', asked: toAsk(first, started.planned) })
      else await end(started, 'done')
    })

  const answer = (chosen: number | null, confidence: Confidence | null) =>
    run(async () => {
      if (!session || phase.kind !== 'question') return
      const { asked } = phase
      const correction = await giveAnswer(session.id, {
        question_id: asked.question.id,
        chosen_option: chosen,
        confidence,
        seconds: Math.round((Date.now() - asked.shownAt) / 1000),
      })
      // The next question is read now: its button says when the queue is over.
      const next = await nextQuestion(session.id)
      const id = asked.question.id
      setAnswered((done) => (done.includes(id) ? done : [...done, id]))
      setPhase({ kind: 'corrected', asked, answered: { chosen, correction }, next })
    })

  const goOn = () =>
    run(async () => {
      if (!session || phase.kind !== 'corrected') return
      if (phase.next === null) await end(session, 'done')
      else if (timeUp) await end(session, 'time')
      else setPhase({ kind: 'question', asked: toAsk(phase.next, session.planned) })
    })

  /** End the session, once its thoughts are planned or dropped (R17). */
  async function end(started: Started, ending: Ending) {
    const thoughts = await getThoughts(started.id)
    if (thoughts.length > 0) setPhase({ kind: 'sorting', thoughts, ending })
    else await close(started, ending)
  }

  async function close(started: Started, ending: Ending) {
    const { minimum_done } = await endSession(started.id, ending !== 'later')
    if (ending === 'later') {
      navigate('/accueil')
      return
    }
    const today = await getToday() // what is left comes back tomorrow, without backlog
    setPhase({ kind: 'ended', ending, rest: today.due, minimumDone: minimum_done })
  }

  const decide = (thought: Thought, plannedFor: string | null) =>
    run(async () => {
      if (!session || phase.kind !== 'sorting') return
      await decideThought(thought.id, plannedFor)
      const thoughts = phase.thoughts.filter((other) => other.id !== thought.id)
      if (thoughts.length > 0) setPhase({ ...phase, thoughts })
      else await close(session, phase.ending)
    })

  function later() {
    if (session) run(() => end(session, 'later'))
    else navigate('/accueil')
  }

  const minimum = day?.after_absence ?? false // after an absence, the minimum alone (R27)
  const due = day?.due ?? 0
  const total = session ? Math.max(session.planned, answered.length) : due
  const title = minimum
    ? 'Séance minimum · File du jour, environ 15 minutes'
    : notion
      ? 'Séance complète · File du jour, puis une notion'
      : 'Séance · File du jour'
  const last = phase.kind === 'corrected' && (phase.next === null || timeUp)
  const nextLabel = last
    ? minimum
      ? 'Terminer la séance'
      : 'Terminer la file du jour'
    : 'Question suivante'

  return (
    <div className="focus">
      <FocusHeader
        label={title}
        action={
          phase.kind !== 'sorting' &&
          phase.kind !== 'ended' && (
            <button type="button" className="button ghost" disabled={busy} onClick={later}>
              {session ? 'Terminer plus tard' : "Retour à l'accueil"}
            </button>
          )
        }
      />
      <main className="focus-main">
        <section className="card session-card" aria-label="Séance">
          {error && <Notice>{error}</Notice>}
          {asking && timeUp && (
            <p className="time-up" role="status">
              <Icon name="timer" />
              <span>
                <strong>Temps écoulé.</strong> Termine cette question : les questions restantes
                reviendront demain, sans retard compté.
              </span>
            </p>
          )}
          {phase.kind === 'ready' &&
            day &&
            (due > 0 ? (
              <>
                <div className="statement">
                  <span className="label">Avant de commencer</span>
                  <h1>
                    {count(due, 'question')} à réviser, environ {queueMinutes(due)} minutes
                  </h1>
                </div>
                <p>
                  Réponds de mémoire, puis dis à quel point tu es sûr de toi. Une pensée te
                  distrait ? Appuie sur P : elle attendra la fin de la séance.
                </p>
                <AwayCheck busy={busy} onStart={start} />
              </>
            ) : (
              <NothingDue notion={notion} />
            ))}
          {(phase.kind === 'question' || phase.kind === 'corrected') && (
            <QuestionCard
              key={phase.asked.shownAt}
              asked={phase.asked}
              answered={phase.kind === 'corrected' ? phase.answered : undefined}
              busy={busy}
              nextLabel={nextLabel}
              onAnswer={answer}
              onNext={goOn}
              onShowCourse={() => setCourse(phase.asked.question)}
            />
          )}
          {phase.kind === 'sorting' && (
            <ThoughtSorting thoughts={phase.thoughts} busy={busy} onDecide={decide} />
          )}
          {phase.kind === 'ended' && (
            <Ended
              ending={phase.ending}
              rest={phase.rest}
              minimumDone={phase.minimumDone}
              minimum={minimum}
              notion={notion}
            />
          )}
        </section>
        {day && (session || due > 0) && (
          <aside className="card session-side" aria-label="Chrono et progression">
            <span className="label">{minimum ? 'Séance minimum' : 'File du jour'}</span>
            <Chrono
              left={left}
              total={SESSION_SECONDS}
              label={left > 0 ? 'restantes sur 15 min' : 'temps écoulé'}
            />
            <Progress done={answered.length} total={total} />
            {session && asking && (
              <FocusTools
                sessionId={session.id}
                questionId={phase.kind === 'question' || phase.kind === 'corrected' ? phase.asked.question.id : null}
              />
            )}
          </aside>
        )}
      </main>
      {course && (
        <ReaderOverlay
          resourceId={course.resource_id}
          page={course.first_page}
          backLabel="Revenir à la question"
          onClose={() => setCourse(undefined)}
        />
      )}
    </div>
  )
}

/** Nothing to review today: the session goes on with a new notion, if one is ready. */
function NothingDue({ notion }: { notion: NotionToStudy | null }) {
  return (
    <>
      <div className="statement">
        <span className="label">File du jour</span>
        <h1>Rien à réviser aujourd'hui</h1>
      </div>
      <p>
        {notion
          ? `Place à une notion nouvelle : ${notion.title}.`
          : "Aucune notion n'est prête pour l'instant : valide les notions d'un chapitre pour en étudier une."}
      </p>
      <div className="actions">
        {notion ? (
          <Link to="/notion" className="button primary">
            Continuer avec une notion
          </Link>
        ) : (
          <Link to="/matieres" className="button primary">
            Voir mes matières
          </Link>
        )}
      </div>
    </>
  )
}

type EndedProps = {
  ending: Ending
  rest: number // the questions still due: they come back tomorrow (R12, R27)
  minimumDone: boolean
  minimum: boolean
  notion: NotionToStudy | null
}

/** The end of the queue: the minimum of the day, then a new notion if one is ready. */
function Ended({ ending, rest, minimumDone, minimum, notion }: EndedProps) {
  const timeUp = ending === 'time'
  const back =
    rest > 0
      ? `${count(rest, 'question')} ${rest > 1 ? 'reviendront' : 'reviendra'} demain, sans retard compté. `
      : ''
  const reached = minimumDone ? 'Le minimum du jour est atteint' : ''
  let label: string
  let title: string
  let text: string
  if (minimum) {
    label = timeUp ? 'Temps écoulé' : 'Séance minimum terminée'
    title = reached || 'La séance est terminée'
    text = `${back}Tu peux t'arrêter là.${notion ? " Si tu as de l'élan, une notion te prend environ 30 minutes." : ''}`
  } else {
    label = timeUp ? 'Temps écoulé' : 'File du jour terminée'
    title = timeUp ? 'Le temps de la file du jour est écoulé' : 'La file du jour est faite'
    text = back + (reached && `${reached}${notion ? " : la suite de la séance, c'est une notion nouvelle." : '.'}`)
  }
  const stop = (primary: boolean) => (
    <Link to="/accueil" className={`button ${primary ? 'primary' : 'ghost'}`}>
      Arrêter
    </Link>
  )
  // The session goes on in full screen: the notion does not ask for the box again.
  const go = (primary: boolean) => (
    <Link
      to="/notion"
      state={{ focused: true }}
      className={`button ${primary ? 'primary' : 'ghost'}`}
    >
      Continuer avec une notion
    </Link>
  )
  return (
    <div className="ended">
      <span className="label">{label}</span>
      <h1>{title}</h1>
      {text && <p>{text}</p>}
      <div className="actions">
        {minimum || !notion ? stop(true) : go(true)}
        {notion && (minimum ? go(false) : stop(false))}
      </div>
    </div>
  )
}
