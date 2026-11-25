import { useEffect, useRef, useState } from 'react'
import { Link, useLocation, useNavigate, useParams } from 'react-router'
import {
  type Confidence,
  decideThought,
  endSession,
  getNextNotion,
  getNotion,
  getNotionPages,
  getThoughts,
  giveAnswer,
  messageOf,
  type NotionSession,
  type NotionToStudy,
  type PageText,
  type QuestionToAsk,
  startNotion,
  type Thought,
} from '../../api.ts'
import { Icon } from '../../components/Icon.tsx'
import { Notice } from '../../components/Notice.tsx'
import { setFullscreen } from '../../fullscreen.ts'
import { AwayCheck } from '../session/AwayCheck.tsx'
import { Chrono } from '../session/Chrono.tsx'
import { FocusHeader } from '../session/FocusHeader.tsx'
import { FocusTools } from '../session/FocusTools.tsx'
import { type Answered, type Asked, QuestionCard } from '../session/QuestionCard.tsx'
import '../session/SessionScreen.css'
import { ThoughtSorting } from '../session/ThoughtSorting.tsx'
import './NotionScreen.css'

/** The steps of a new notion (R13), with their time; exercises come with lot 4. */
type Step = 'warmup' | 'pretest' | 'reading' | 'test' | 'pause'
type AskingStep = 'warmup' | 'pretest' | 'test'

const STEPS: Record<Step, { name: string; seconds: number }> = {
  warmup: { name: 'Échauffement', seconds: 3 * 60 },
  pretest: { name: 'Prétest', seconds: 2 * 60 },
  reading: { name: 'Lecture', seconds: 10 * 60 },
  test: { name: 'Test', seconds: 3 * 60 },
  pause: { name: 'Pause', seconds: 5 * 60 }, // R15
}
const ORDER = ['warmup', 'pretest', 'reading', 'test'] as const // then the end, the pause

/** What the banner says when the time of a step is up. */
const TIME_UP: Record<Exclude<Step, 'pause'>, [string, string]> = {
  warmup: ['Temps écoulé.', 'Termine ta réponse, puis on passe au prétest.'],
  pretest: ['Temps écoulé.', "Pas besoin d'avoir tout deviné : passe à la lecture."],
  reading: ['Temps de lecture écoulé.', 'On passe au test.'],
  test: ['Temps écoulé.', 'Termine le test à ton rythme : il ne se saute pas.'],
}

type Phase =
  | { kind: 'loading' }
  | { kind: 'none' } // no notion has its questions yet
  | { kind: 'ready'; notion: NotionToStudy } // R16: the box to tick, then Commencer
  | { kind: 'question'; step: AskingStep; index: number; asked: Asked; answered?: Answered }
  | { kind: 'reading' }
  | { kind: 'sorting'; thoughts: Thought[]; ending: 'done' | 'later' } // R17
  | { kind: 'pause'; next: NotionToStudy | null } // R15

/** A pretest answered: its correction waits for the reading. */
type Pretested = { question: QuestionToAsk; answered: Answered }

/** Notion: a new notion in full screen, as the queue (R16). A question already
 *  succeeded to warm up (R15), the pretests, the guided reading of its pages, then the
 *  test, whose answers enter the reviews (R13); a pause of 5 minutes, after which the
 *  next notion starts (R15). Exercises come with lot 4, the "why?" question with lot 3. */
export function NotionScreen() {
  const navigate = useNavigate()
  const { notionId } = useParams()
  // Coming from the end of the queue, the session already runs in full screen.
  const focused = (useLocation().state as { focused?: boolean } | null)?.focused ?? false
  const [phase, setPhase] = useState<Phase>({ kind: 'loading' })
  const [study, setStudy] = useState<NotionSession>()
  const [pages, setPages] = useState<PageText[]>([])
  const [pretested, setPretested] = useState<Pretested[]>([])
  const [rank, setRank] = useState(0) // notions begun on this screen
  const [step, setStep] = useState<Step>('pretest')
  const [stepStart, setStepStart] = useState(() => Date.now())
  const [now, setNow] = useState(() => Date.now())
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string>()
  const working = useRef(false) // a call is on its way: another one is not sent
  const loaded = useRef(false) // read once, even when React runs the effects twice

  useEffect(() => {
    if (loaded.current) return
    loaded.current = true
    const read = notionId ? getNotion(Number(notionId)) : getNextNotion()
    read.then(
      (notion) => {
        if (!notion) setPhase({ kind: 'none' })
        else if (focused) begin(notion)
        else setPhase({ kind: 'ready', notion })
      },
      (reason: unknown) => setError(messageOf(reason)),
    )
  }, [])
  useEffect(() => () => setFullscreen(false), []) // leaving the screen leaves the full screen

  // Each step has its clock; the reading hides its text when its time is up.
  const timed = phase.kind === 'question' || phase.kind === 'reading' || phase.kind === 'pause'
  useEffect(() => {
    if (!timed) return
    const timer = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(timer)
  }, [timed])
  const total = STEPS[step].seconds
  const left = Math.min(total, Math.max(0, total - Math.floor((now - stepStart) / 1000)))
  const timeUp = left === 0

  // R15: at the end of the pause, the next notion starts, with its question of reprise.
  useEffect(() => {
    if (phase.kind === 'pause' && timeUp && phase.next) begin(phase.next)
  }, [phase, timeUp])

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

  const begin = (notion: NotionToStudy) =>
    run(async () => {
      setFullscreen(true)
      const started = await startNotion(notion.id)
      setPages(await getNotionPages(notion.id))
      setStudy(started)
      setPretested([])
      setRank((n) => n + 1)
      await enter(started, 'warmup')
    })

  /** Show a step from its start; a step without questions is passed. */
  async function enter(started: NotionSession, next: (typeof ORDER)[number]) {
    if (next !== 'reading' && questionsOf(started, next).length === 0) {
      await after(started, next)
      return
    }
    const at = Date.now()
    setStep(next)
    setStepStart(at)
    setNow(at)
    if (next === 'reading') setPhase({ kind: 'reading' })
    else setPhase({ kind: 'question', step: next, index: 0, asked: toAsk(started, next, 0) })
  }

  /** What follows a step: the next one, or the end of the notion after the test. */
  async function after(started: NotionSession, current: (typeof ORDER)[number]) {
    const next = ORDER[ORDER.indexOf(current) + 1]
    if (next) await enter(started, next)
    else await end(started, 'done')
  }

  const answer = (chosen: number | null, confidence: Confidence | null) =>
    run(async () => {
      if (!study || phase.kind !== 'question') return
      const { asked } = phase
      const correction = await giveAnswer(study.session_id, {
        question_id: asked.question.id,
        chosen_option: chosen,
        confidence,
        seconds: Math.round((Date.now() - asked.shownAt) / 1000),
      })
      const answered = { chosen, correction }
      if (phase.step === 'pretest') {
        setPretested((done) => [...done, { question: asked.question, answered }])
      }
      setPhase({ ...phase, answered })
    })

  const goOn = () =>
    run(async () => {
      if (!study || phase.kind !== 'question') return
      const index = phase.index + 1
      if (index < questionsOf(study, phase.step).length) {
        setPhase({ kind: 'question', step: phase.step, index, asked: toAsk(study, phase.step, index) })
      } else {
        await after(study, phase.step)
      }
    })

  /** End the notion, once its thoughts are planned or dropped (R17). */
  async function end(started: NotionSession, ending: 'done' | 'later') {
    const thoughts = await getThoughts(started.session_id)
    if (thoughts.length > 0) setPhase({ kind: 'sorting', thoughts, ending })
    else await close(started, ending)
  }

  async function close(started: NotionSession, ending: 'done' | 'later') {
    await endSession(started.session_id, ending === 'done') // done: the notion is studied
    if (ending === 'later') {
      navigate('/accueil')
      return
    }
    const next = await getNextNotion()
    const at = Date.now()
    setStep('pause')
    setStepStart(at)
    setNow(at)
    setPhase({ kind: 'pause', next })
  }

  const decide = (thought: Thought, plannedFor: string | null) =>
    run(async () => {
      if (!study || phase.kind !== 'sorting') return
      await decideThought(thought.id, plannedFor)
      const thoughts = phase.thoughts.filter((other) => other.id !== thought.id)
      if (thoughts.length > 0) setPhase({ ...phase, thoughts })
      else await close(study, phase.ending)
    })

  const open = phase.kind === 'question' || phase.kind === 'reading' // a session runs
  function later() {
    if (study && open) run(() => end(study, 'later'))
    else navigate('/accueil')
  }

  const shown = study?.notion ?? (phase.kind === 'ready' ? phase.notion : undefined)
  const title = shown
    ? `Séance · Notion ${Math.max(rank, 1)} · ${shown.subject}, ${shown.title}`
    : 'Séance · Notion'
  const steps: Step[] = [
    ...(study?.warmup ? (['warmup'] as const) : []),
    'pretest',
    'reading',
    'test',
    'pause',
  ]
  const current = steps.indexOf(step)

  return (
    <div className="focus">
      <FocusHeader
        label={title}
        action={
          phase.kind !== 'sorting' && (
            <button type="button" className="button ghost" disabled={busy} onClick={later}>
              {open ? 'Terminer plus tard' : "Retour à l'accueil"}
            </button>
          )
        }
      />
      <main className="focus-main">
        <section
          className={`card session-card${phase.kind === 'reading' ? ' reading' : ''}`}
          aria-label={STEPS[step].name}
        >
          {error && <Notice>{error}</Notice>}
          {(phase.kind === 'question' || phase.kind === 'reading') && timeUp && step !== 'pause' && (
            <p className="time-up" role="status">
              <Icon name="timer" />
              <span>
                <strong>{TIME_UP[step][0]}</strong> {TIME_UP[step][1]}
              </span>
            </p>
          )}
          {phase.kind === 'none' && (
            <>
              <div className="statement">
                <span className="label">Notion</span>
                <h1>Aucune notion n'est prête</h1>
              </div>
              <p>
                Valide les notions d'un chapitre : Claude écrit leurs questions, puis tu pourras
                les étudier.
              </p>
              <div className="actions">
                <Link to="/matieres" className="button primary">
                  Voir mes matières
                </Link>
              </div>
            </>
          )}
          {phase.kind === 'ready' && (
            <>
              <div className="statement">
                <span className="label">Avant de commencer · {phase.notion.subject}</span>
                <h1>{phase.notion.title}</h1>
              </div>
              <p>
                {phase.notion.summary} Prétest, lecture de 10 minutes au plus, puis test : une
                vingtaine de minutes.
              </p>
              <AwayCheck busy={busy} onStart={() => begin(phase.notion)} />
            </>
          )}
          {phase.kind === 'question' && study && (
            <>
              <QuestionCard
                key={phase.asked.shownAt}
                asked={phase.asked}
                answered={phase.answered}
                reveal={phase.step !== 'pretest'}
                note={
                  phase.step === 'pretest'
                    ? 'QCM · ta réponse est notée, la correction viendra avec ta lecture'
                    : undefined
                }
                busy={busy}
                nextLabel={nextLabel(study, phase.step, phase.index)}
                onAnswer={answer}
                onNext={goOn}
              />
              {phase.step === 'pretest' && timeUp && !phase.answered && (
                <div className="actions">
                  <button
                    type="button"
                    className="button ghost"
                    disabled={busy}
                    onClick={() => run(() => enter(study, 'reading'))}
                  >
                    Passer à la lecture
                  </button>
                </div>
              )}
            </>
          )}
          {phase.kind === 'reading' && study && (
            <Reading
              pretested={pretested}
              pages={pages}
              hidden={timeUp}
              busy={busy}
              onDone={() => run(() => after(study, 'reading'))}
            />
          )}
          {phase.kind === 'sorting' && (
            <ThoughtSorting thoughts={phase.thoughts} busy={busy} onDecide={decide} />
          )}
          {phase.kind === 'pause' && (
            <Pause
              next={phase.next}
              busy={busy}
              onShorten={() => phase.next && begin(phase.next)}
              onStop={() => navigate('/accueil')}
            />
          )}
        </section>
        {study && (
          <aside className="card session-side" aria-label="Chrono et étapes">
            <span className="label">
              Étape {current + 1} sur {steps.length} · {STEPS[step].name}
            </span>
            <div className="step-dots" aria-hidden="true">
              {steps.map((name, k) => (
                <span key={name} className={stage(k, current)} />
              ))}
            </div>
            <Chrono
              left={left}
              total={total}
              label={left > 0 ? 'restantes' : step === 'pause' ? 'pause terminée' : 'temps écoulé'}
            />
            <ol className="step-list">
              {steps.map((name, k) => (
                <li key={name} className={stage(k, current)}>
                  <span className="step-dot" />
                  <span>{STEPS[name].name}</span>
                  <span className="mono">{STEPS[name].seconds / 60} min</span>
                </li>
              ))}
            </ol>
            {open && (
              <FocusTools
                sessionId={study.session_id}
                questionId={phase.kind === 'question' ? phase.asked.question.id : null}
              />
            )}
          </aside>
        )}
      </main>
    </div>
  )
}

function questionsOf(started: NotionSession, step: AskingStep): QuestionToAsk[] {
  if (step === 'warmup') return started.warmup ? [started.warmup] : []
  return step === 'pretest' ? started.pretests : started.tests
}

function toAsk(started: NotionSession, step: AskingStep, index: number): Asked {
  const questions = questionsOf(started, step)
  const label =
    step === 'warmup'
      ? 'Échauffement · une question déjà réussie'
      : step === 'pretest'
        ? `Prétest ${index + 1} sur ${questions.length} · avant de lire`
        : `Test ${index + 1} sur ${questions.length} · ${started.notion.title}`
  return { question: questions[index], label, shownAt: Date.now() }
}

/** The button after a question: the next one, or what follows its step. */
function nextLabel(started: NotionSession, step: AskingStep, index: number): string {
  if (index + 1 < questionsOf(started, step).length) return 'Question suivante'
  if (step === 'warmup') return 'Passer au prétest'
  if (step === 'pretest') return 'Commencer la lecture'
  return 'Terminer la notion'
}

/** A step before the current one is done; those after it are to come. */
function stage(k: number, current: number): string | undefined {
  if (k < current) return 'done'
  return k === current ? 'current' : undefined
}

type ReadingProps = {
  pretested: Pretested[]
  pages: PageText[]
  hidden: boolean // the time is up: the answers are looked for from memory
  busy: boolean
  onDone: () => void
}

/** The guided reading: what to look for, then the pages of the notion, at most 10
 *  minutes. The pages are shown as their text; the reader shows them as they are. */
function Reading({ pretested, pages, hidden, busy, onDone }: ReadingProps) {
  return (
    <>
      <span className="label">Lecture guidée · 10 minutes au plus</span>
      {pretested.length > 0 && (
        <div className="reading-goals">
          <span className="label">Cherche les réponses à tes questions du prétest</span>
          <ul>
            {pretested.map(({ question, answered }) => (
              <li key={question.id}>
                <span lang="en">{question.statement}</span>
                <PretestCheck question={question} answered={answered} />
              </li>
            ))}
          </ul>
        </div>
      )}
      {/* Only the pages scroll: what to look for and the way on stay in view. */}
      <div className="reading-pages">
      {hidden ? (
        <div className="reading-hidden">
          <span className="reading-hidden-title">Le texte est masqué</span>
          <span>
            C'est en cherchant les réponses de mémoire que tu retiens, pas en relisant. Tu
            pourras revenir au cours après le test.
          </span>
        </div>
      ) : (
        pages.map((page) => (
          <article key={page.number} className="course-page" aria-label={`Page ${page.number}`}>
            {page.text.trim() && <p className="course-text">{page.text.trim()}</p>}
            {page.description && (
              <p className="course-description">
                <strong>Ce que montre la page.</strong> {page.description}
              </p>
            )}
            <p className="course-number">{page.number}</p>
          </article>
        ))
      )}
      </div>
      <div className="actions">
        <button type="button" className="button primary" disabled={busy} onClick={onDone}>
          J'ai lu, passer au test
        </button>
      </div>
    </>
  )
}

/** The correction of a pretest, folded: to look at once the answer is found. */
function PretestCheck({ question, answered }: Pretested) {
  const { chosen, correction } = answered
  const right = question.options.find((option) => option.number === correction.correct_option)
  const verdict = correction.correct
    ? 'Tu avais vu juste.'
    : chosen === null
      ? "Tu n'avais pas d'idée : c'est normal avant de lire."
      : "Ta réponse n'était pas la bonne : c'est normal avant de lire."
  return (
    <details className="detail">
      <summary>Vérifier</summary>
      {verdict} Bonne réponse : <span lang="en">{right?.text}</span>.{' '}
      {correction.explanations[correction.correct_option - 1]}
    </details>
  )
}

type PauseProps = {
  next: NotionToStudy | null
  busy: boolean
  onShorten: () => void
  onStop: () => void
}

/** R15: a fixed pause of 5 minutes; the next notion starts when it ends. */
function Pause({ next, busy, onShorten, onStop }: PauseProps) {
  return (
    <div className="ended">
      <span className="label">Pause fixe</span>
      <h1>Pause de 5 minutes</h1>
      <p className="pause-text">
        La notion est terminée. Profite de la pause pour laisser ton cerveau consolider ce que
        tu viens d'apprendre.
      </p>
      <ul className="pause-tips">
        <li>Lève-toi, bois de l'eau, regarde au loin.</li>
        <li>Laisse le téléphone de côté : c'est lui qui transforme 5 minutes en 30.</li>
      </ul>
      <div className="next-box">
        <span className="label">Ensuite</span>
        {next
          ? `${next.subject} · ${next.title}. Elle commence à la fin du compte à rebours.`
          : "Aucune autre notion n'est prête : la séance peut s'arrêter là."}
      </div>
      <div className="actions">
        {next ? (
          <>
            <button type="button" className="button secondary" disabled={busy} onClick={onShorten}>
              Écourter la pause
            </button>
            <button type="button" className="button ghost" onClick={onStop}>
              Terminer la session
            </button>
          </>
        ) : (
          <button type="button" className="button primary" onClick={onStop}>
            Terminer la session
          </button>
        )}
      </div>
    </div>
  )
}
