import { useEffect, useEffectEvent, useState } from 'react'
import {
  type ExerciseView,
  type GradingState,
  messageOf,
  type QuestionToAsk,
  sendOpenAnswer,
} from '../../api.ts'
import { Icon } from '../../components/Icon.tsx'
import { Notice } from '../../components/Notice.tsx'
import { notForShortcuts } from '../../study.ts'
import {
  type Answered,
  type Asked,
  ClaimNote,
  CriteriaChecked,
  type Given,
  GradingNotes,
  useClaim,
  useGrading,
} from './QuestionCard.tsx'

const KINDS = { worked: 'Exemple résolu', completion: 'À compléter', solo: 'Seul' }

type Props = {
  asked: Asked // its question has its exercise view
  answered?: Answered // once answered
  tabs?: QuestionToAsk[] // the exercises of the step of a notion, as tabs
  sessionId: number // where a written answer is sent
  busy: boolean
  nextLabel: string
  onAnswer: (given: Given) => void
  onGraded?: (grading: GradingState) => void // a written answer graded after
  onClaimed?: (answerId: number, claimId: number) => void // Je pense avoir juste
  onNext: () => void
  onShowCourse?: () => void // Voir le cours: its pages in the reader (R4)
}

/** What a kind of exercise asks, under its statement (Notion mockup); a solo problem
 *  follows the other two in the step of its notion, and comes alone in a review. */
function introOf(exercise: ExerciseView, value: boolean, inStep: boolean): string {
  if (exercise.kind === 'worked') {
    return "Lis chaque étape et vérifie que tu comprends d'où elle vient."
  }
  if (exercise.kind === 'completion') {
    const count = exercise.given.length
    const done =
      count < 2 ? 'La première étape est faite.' : `Les ${count} premières étapes sont faites.`
    return `${done} ${value ? 'Termine le calcul.' : 'Écris la suite du raisonnement.'}`
  }
  const none = inStep ? "Cette fois, aucune étape n'est donnée" : "Aucune étape n'est donnée"
  return value
    ? `${none}. Fais le calcul sur papier si besoin.`
    : `${none} : écris ton raisonnement en entier.`
}

/** An exercise (T3, R14): an example worked step by step, to read; a problem to
 *  complete; or a problem to solve alone, which in a review offers the worked example
 *  of its notion until two are solved in a row. Only its result is answered, without
 *  confidence: a value, graded by the code, or a reasoning or code, graded by Claude on
 *  the steps of its solution (T6). Then the whole solution shows. */
export function ExerciseCard({
  asked,
  answered,
  tabs,
  sessionId,
  busy,
  nextLabel,
  onAnswer,
  onGraded,
  onClaimed,
  onNext,
  onShowCourse,
}: Props) {
  const { question } = asked
  const exercise = question.exercise
  const [text, setText] = useState('')
  const [sent, setSent] = useState<number>() // when a written answer went to Claude
  const [sending, setSending] = useState(false)
  const [problem, setProblem] = useState<string>()
  const { grading, late, canGoOn } = useGrading(answered, sent, onGraded)
  const worked = exercise?.kind === 'worked'
  const value = question.format === 'value'
  const ready = text.trim() !== '' && !sending && !busy

  /** Check a value at once; send a written answer to Claude, with its time. */
  async function check() {
    if (!ready) return
    if (value) {
      onAnswer({ chosen: null, text: text.trim(), confidence: null, gradingId: null })
      return
    }
    setSending(true)
    setProblem(undefined)
    try {
      const seconds = Math.round((Date.now() - asked.shownAt) / 1000)
      const { id } = await sendOpenAnswer(sessionId, {
        question_id: question.id,
        answer_text: text.trim(),
        seconds,
      })
      setSent(Date.now())
      onAnswer({ chosen: null, text: text.trim(), confidence: null, gradingId: id })
    } catch (reason) {
      setProblem(messageOf(reason))
    } finally {
      setSending(false)
    }
  }

  // Entrée goes on once the example is read, or the answer corrected.
  const onKey = useEffectEvent((event: KeyboardEvent) => {
    if (notForShortcuts(event) || busy || event.key !== 'Enter') return
    if (event.target instanceof HTMLButtonElement) return // a button does its own action
    if (worked || (answered && canGoOn)) {
      event.preventDefault()
      onNext()
    }
  })
  useEffect(() => {
    const listener = (event: KeyboardEvent) => onKey(event)
    document.addEventListener('keydown', listener)
    return () => document.removeEventListener('keydown', listener)
  }, [])

  if (!exercise) return null
  const verdict = answered?.correction
    ? answered.correction.correct
    : grading?.status === 'done'
      ? grading.correct
      : null
  return (
    <>
      <div className="question-head">
        <span className="label">
          Exercice · <span lang="en">{exercise.topic}</span>
        </span>
        {verdict !== null &&
          (verdict ? (
            <span className="badge correct">
              <Icon name="check" size={14} />
              Juste
            </span>
          ) : (
            <span className="badge review">
              <Icon name="redo" size={14} />À revoir
            </span>
          ))}
      </div>
      {tabs && tabs.length > 1 && <ExerciseTabs tabs={tabs} current={question.id} />}
      <div className="statement">
        <h1 lang="en">{question.statement}</h1>
        <p className="exercise-intro">{introOf(exercise, value, tabs !== undefined)}</p>
      </div>
      {exercise.worked_example && !answered && (
        <details className="worked-example">
          <summary>Revoir l'exemple résolu</summary>
          <p className="worked-example-statement" lang="en">
            {exercise.worked_example.statement}
          </p>
          <Steps steps={exercise.worked_example.steps} />
        </details>
      )}
      {exercise.given.length > 0 && !answered && <Steps steps={exercise.given} />}
      {problem && <Notice>{problem}</Notice>}
      {!worked && !answered && (
        <AnswerField
          value={value}
          kind={exercise.kind}
          text={text}
          ready={ready}
          sending={sending}
          onChange={setText}
          onCheck={() => void check()}
        />
      )}
      {answered && (
        <ExerciseCorrected
          asked={asked}
          answered={answered}
          grading={grading}
          late={late}
          busy={busy}
          nextLabel={nextLabel}
          onClaimed={onClaimed}
          onNext={onNext}
          onShowCourse={onShowCourse}
        />
      )}
      {worked && (
        <div className="actions">
          <button type="button" className="button primary" disabled={busy} onClick={onNext}>
            {nextLabel}
          </button>
          {onShowCourse && (
            <button type="button" className="button ghost" onClick={onShowCourse}>
              Voir le cours
            </button>
          )}
        </div>
      )}
    </>
  )
}

type FieldProps = {
  value: boolean
  kind: ExerciseView['kind']
  text: string
  ready: boolean
  sending: boolean // a written answer on its way to Claude
  onChange: (text: string) => void
  onCheck: () => void
}

/** The result of the exercise: a number with "Vérifier" (mockup), or a reasoning or
 *  code, sent to Claude with Entrée. */
function AnswerField({ value, kind, text, ready, sending, onChange, onCheck }: FieldProps) {
  if (value) {
    return (
      <div className="answer-line">
        <label htmlFor="exercise-answer" className="label">
          Ton résultat
        </label>
        <div className="exercise-check">
          <input
            id="exercise-answer"
            className="field mono"
            type="text"
            autoComplete="off"
            spellCheck={false}
            autoFocus
            placeholder="Par exemple 2,5"
            value={text}
            onChange={(event) => onChange(event.target.value)}
            onKeyDown={(event) => {
              if (event.key !== 'Enter') return
              event.preventDefault()
              onCheck()
            }}
          />
          <button type="button" className="button primary" disabled={!ready} onClick={onCheck}>
            Vérifier
          </button>
        </div>
      </div>
    )
  }
  return (
    <div className="answer-text">
      <label htmlFor="exercise-answer" className="label">
        Ta réponse
      </label>
      <textarea
        id="exercise-answer"
        className="field"
        rows={kind === 'solo' ? 6 : 4}
        autoFocus
        placeholder={
          kind === 'solo'
            ? 'Écris ton raisonnement, étape par étape…'
            : 'Écris les étapes qui manquent…'
        }
        value={text}
        readOnly={sending}
        onChange={(event) => onChange(event.target.value)}
        onKeyDown={(event) => {
          if (event.key !== 'Enter' || event.shiftKey || event.nativeEvent.isComposing) {
            return // Maj+Entrée goes to the line
          }
          event.preventDefault()
          onCheck()
        }}
      />
      <span className="hint">
        Entrée envoie ta réponse à Claude, qui la corrige étape par étape ; Maj+Entrée va à
        la ligne.
      </span>
      <div className="actions">
        <button type="button" className="button primary" disabled={!ready} onClick={onCheck}>
          Envoyer
        </button>
      </div>
    </div>
  )
}

type CorrectedProps = {
  asked: Asked
  answered: Answered
  grading?: GradingState
  late: boolean
  busy: boolean
  nextLabel: string
  onClaimed?: (answerId: number, claimId: number) => void
  onNext: () => void
  onShowCourse?: () => void
}

/** The correction of an exercise: the answer, the steps that Claude checked with the
 *  points and the step where the student dropped off (T6), what was expected, then the
 *  whole solution. While Claude grades, only the wait shows, 15 s at most. */
function ExerciseCorrected({
  asked,
  answered,
  grading,
  late,
  busy,
  nextLabel,
  onClaimed,
  onNext,
  onShowCourse,
}: CorrectedProps) {
  const { question } = asked
  const { text, correction } = answered
  const { claimable, claimed, claiming, problem, claim } = useClaim(
    question,
    answered,
    onClaimed,
  )
  if (grading?.status === 'pending' && !late) {
    return (
      <p className="grading-wait" role="status">
        <span className="wait-dots" aria-hidden="true">
          <span />
          <span />
          <span />
        </span>
        Claude corrige ta réponse, étape par étape…
      </p>
    )
  }
  const given = question.exercise?.given.length ?? 0
  const solution = correction?.solution ?? grading?.solution ?? []
  return (
    <>
      <div className="given">
        <span className="label">Ta réponse</span>
        {text ?? 'Je ne sais pas'}
      </div>
      {grading && <GradingNotes grading={grading} />}
      {grading?.status === 'done' && (
        <CriteriaChecked
          grading={grading}
          title={`Étapes vérifiées par ${grading.provisional ? 'le modèle local' : 'Claude'}`}
          summary={pointsOf(grading, given)}
        />
      )}
      {correction && (
        <span className="exercise-expected">
          Réponse attendue : <strong>{correction.expected}</strong>
        </span>
      )}
      {solution.length > 0 && (
        <div className="correction">
          <span className="label">Solution</span>
          <Steps steps={solution} />
        </div>
      )}
      <ClaimNote claimed={claimed} problem={problem} />
      <div className="actions">
        <button type="button" className="button primary" disabled={busy} onClick={onNext}>
          {nextLabel}
        </button>
        {onShowCourse && (
          <button type="button" className="button ghost" onClick={onShowCourse}>
            Voir le cours
          </button>
        )}
        {claimable && (
          <button
            type="button"
            className="button ghost"
            disabled={claiming}
            onClick={() => void claim()}
          >
            Je pense avoir juste
          </button>
        )}
      </div>
    </>
  )
}

/** The points of an exercise graded by Claude, and the step where the student dropped
 *  off, numbered in the whole solution (its given steps first). */
function pointsOf(grading: GradingState, given: number): string | undefined {
  const { points, out_of: outOf, dropped_at: droppedAt } = grading
  if (points === null || outOf === null) return undefined
  const earned = `${points} ${points < 2 ? 'point' : 'points'} sur ${outOf}`
  return droppedAt === null ? earned : `${earned} · tu as décroché à l'étape ${given + droppedAt}`
}

/** The steps of a solution, numbered. */
export function Steps({ steps }: { steps: string[] }) {
  return (
    <ol className="exercise-steps">
      {steps.map((step, index) => (
        <li key={index}>
          <span className="mono">{index + 1}</span>
          <span lang="en">{step}</span>
        </li>
      ))}
    </ol>
  )
}

/** The exercises of the step of a notion, as in the mockup: the one in progress. */
function ExerciseTabs({ tabs, current }: { tabs: QuestionToAsk[]; current: number }) {
  return (
    <div role="list" aria-label="Étapes de l'exercice" className="exercise-tabs">
      {tabs.map((tab, index) => (
        <span
          key={tab.id}
          role="listitem"
          aria-current={tab.id === current ? 'step' : undefined}
          className={tab.id === current ? 'current' : undefined}
        >
          <span className="mono">{index + 1}</span>
          {tab.exercise ? KINDS[tab.exercise.kind] : ''}
        </span>
      ))}
    </div>
  )
}
