import { useEffect, useEffectEvent, useState } from 'react'
import {
  claimAnswer,
  type Confidence,
  type Correction,
  type GradingState,
  getGrading,
  giveAnswer,
  giveConfidence,
  messageOf,
  type QuestionToAsk,
  sendOpenAnswer,
} from '../../api.ts'
import { Icon } from '../../components/Icon.tsx'
import { Notice } from '../../components/Notice.tsx'
import { notForShortcuts } from '../../study.ts'

/** A question on screen, with the label of its place in the queue. */
export type Asked = { question: QuestionToAsk; label: string; shownAt: number }

/** An answer as it is validated: an option or a text (both null: "Je ne sais pas"), its
 *  confidence (R6), and for an open answer the grading already asked of Claude (T6). */
export type Given = {
  chosen: number | null
  text: string | null
  confidence: Confidence | null
  gradingId: number | null
}

/** An answer validated, with its correction: by the code (T5), or by Claude (T6). */
export type Answered = Given & { correction?: Correction; grading?: GradingState }

/** Validate an answer: graded at once by the code (T5), or, for an open answer already
 *  sent to Claude, given its confidence (T6), its grading perhaps still on its way. A
 *  written exercise asks no confidence: its grading is read as it stands (T3). */
export async function validated(
  sessionId: number,
  asked: Asked,
  given: Given,
): Promise<Answered> {
  const seconds = Math.round((Date.now() - asked.shownAt) / 1000)
  if (given.gradingId !== null && given.confidence !== null) {
    const confidence = given.confidence
    const grading = await giveConfidence(given.gradingId, { confidence, seconds })
    return { ...given, grading }
  }
  if (given.gradingId !== null) return { ...given, grading: await getGrading(given.gradingId) }
  const correction = await giveAnswer(sessionId, {
    question_id: asked.question.id,
    chosen_option: given.chosen,
    answer_text: given.text,
    confidence: given.confidence,
    seconds,
  })
  return { ...given, correction }
}

type Props = {
  asked: Asked
  answered?: Answered // once validated
  reveal?: boolean // false for a pretest: noted, its correction waits for the reading
  note?: string // under the statement: the format and how it is corrected
  sessionId: number // where an open answer is sent
  busy: boolean
  nextLabel: string
  onAnswer: (given: Given) => void
  onGraded?: (grading: GradingState) => void // an open answer graded after its validation
  onClaimed?: (answerId: number, claimId: number) => void // Je pense avoir juste (T5)
  onNext: () => void
  onShowCourse?: () => void // Voir le cours: its pages in the reader (R4)
}

const LETTERS = ['A', 'B', 'C', 'D']
const LEVELS: { confidence: Confidence; name: string; dots: number }[] = [
  { confidence: 'sure', name: 'Sûr', dots: 3 },
  { confidence: 'hesitant', name: 'Hésitant', dots: 2 },
  { confidence: 'guess', name: 'Au hasard', dots: 1 },
]
const WAIT_SECONDS = 15 // T6: then the session goes on, and the grading comes at the end
const READ_EVERY_MS = 700 // how often a grading on its way is read

/** The grading by Claude of an answer validated, read until it ends (T6): late after 15
 *  seconds of waiting since it was sent, when the session goes on. */
export function useGrading(
  answered: Answered | undefined,
  sentAt: number | undefined,
  onGraded?: (grading: GradingState) => void,
) {
  const [read, setRead] = useState<GradingState>() // the grading, read since validated
  const [now, setNow] = useState(() => Date.now())
  const grading = read ?? answered?.grading
  const waiting = grading?.status === 'pending'
  const late = waiting && sentAt !== undefined && now - sentAt >= WAIT_SECONDS * 1000

  const graded = useEffectEvent((state: GradingState) => {
    setRead(state)
    onGraded?.(state)
  })
  const gradingId = waiting ? grading?.id : undefined
  useEffect(() => {
    if (gradingId === undefined) return
    const timer = setInterval(() => {
      setNow(Date.now())
      getGrading(gradingId).then(
        (state) => {
          if (state.status !== 'pending') graded(state)
        },
        () => {}, // read again at the next turn
      )
    }, READ_EVERY_MS)
    return () => clearInterval(timer)
  }, [gradingId])
  return { grading, waiting, late, canGoOn: !waiting || late }
}

/** Je pense avoir juste (T5): a value or a short answer that the code found wrong goes
 *  to Claude in the background, and the session goes on. */
export function useClaim(
  question: QuestionToAsk,
  answered: Answered | undefined,
  onClaimed?: (answerId: number, claimId: number) => void,
) {
  const [claimed, setClaimed] = useState(false)
  const [claiming, setClaiming] = useState(false)
  const [problem, setProblem] = useState<string>()
  const correction = answered?.correction
  const claimable =
    (question.format === 'value' || question.format === 'short') &&
    correction !== undefined &&
    !correction.correct &&
    answered?.text !== null &&
    !claimed

  async function claim() {
    if (!correction) return
    setClaiming(true)
    setProblem(undefined)
    try {
      const { id } = await claimAnswer(correction.answer_id)
      setClaimed(true)
      onClaimed?.(correction.answer_id, id)
    } catch (reason) {
      setProblem(messageOf(reason))
    } finally {
      setClaiming(false)
    }
  }

  return { claimable, claimed, claiming, problem, claim }
}

/** What follows "Je pense avoir juste": the message of the mockup, or why it failed. */
export function ClaimNote({ claimed, problem }: { claimed: boolean; problem?: string }) {
  return (
    <>
      {claimed && (
        <p className="hint claim-sent" role="status">
          Envoyé à Claude. S'il te donne raison, la question sera reprogrammée comme juste et
          ta formulation ajoutée aux réponses acceptées.
        </p>
      )}
      {problem && <Notice>{problem}</Notice>}
    </>
  )
}

/** Under the statement: the format of the question and how it is corrected. */
function noteOf(question: QuestionToAsk): string {
  if (question.format === 'value') {
    const percent = ((question.tolerance ?? 0.01) * 100).toLocaleString('fr-FR', {
      maximumFractionDigits: 2,
    })
    return `Valeur · corrigée instantanément, à ${percent} % près`
  }
  if (question.format === 'short') return 'Réponse courte · corrigée instantanément'
  if (question.format === 'open') return 'Réponse ouverte · corrigée par Claude'
  return 'QCM · corrigé instantanément'
}

/** A question of the queue: its options or its field, and the confidence (R6), then its
 *  correction. Keys: A to D for an option, 1 to 3 for the confidence, Entrée to go on.
 *  In a field, Entrée leaves it for the confidence; an open answer then goes to Claude,
 *  who grades it while the confidence is chosen (T6). */
export function QuestionCard({
  asked,
  answered,
  reveal = true,
  note,
  sessionId,
  busy,
  nextLabel,
  onAnswer,
  onGraded,
  onClaimed,
  onNext,
  onShowCourse,
}: Props) {
  const [chosen, setChosen] = useState<number>()
  const [text, setText] = useState('')
  const [confidence, setConfidence] = useState<Confidence>()
  const [sent, setSent] = useState<{ id: number; at: number }>() // to Claude (T6)
  const [sending, setSending] = useState(false)
  const [problem, setProblem] = useState<string>()
  const { question } = asked
  const open = question.format === 'open'
  const written = question.format !== 'mcq' // a field: a value, a short or an open answer
  const given = written ? text.trim() !== '' : chosen !== undefined
  const ready = given && confidence !== undefined && !sending
  const { grading, late, canGoOn } = useGrading(answered, sent?.at, onGraded)

  /** Send an open answer to Claude at once; its grading, or nothing if it failed. */
  async function send(): Promise<number | undefined> {
    if (sent) return sent.id
    setSending(true)
    setProblem(undefined)
    try {
      const { id } = await sendOpenAnswer(sessionId, {
        question_id: question.id,
        answer_text: text.trim(),
      })
      setSent({ id, at: Date.now() })
      return id
    } catch (reason) {
      setProblem(messageOf(reason))
      return undefined
    } finally {
      setSending(false)
    }
  }

  async function validate() {
    if (!ready || confidence === undefined) return
    if (open) {
      const gradingId = await send()
      if (gradingId !== undefined) {
        onAnswer({ chosen: null, text: text.trim(), confidence, gradingId })
      }
      return
    }
    onAnswer({
      chosen: written ? null : (chosen ?? null),
      text: written ? text.trim() : null,
      confidence,
      gradingId: null,
    })
  }

  const onKey = useEffectEvent((event: KeyboardEvent) => {
    if (notForShortcuts(event) || busy) return
    if (event.key === 'Enter') {
      // A button pressed with Entrée does its own action; an option or a level does not.
      const target = event.target
      if (target instanceof HTMLButtonElement && target.getAttribute('role') !== 'radio') return
      event.preventDefault()
      if (!answered) void validate()
      else if (canGoOn) onNext()
      return
    }
    if (answered) return
    const option = question.options[LETTERS.indexOf(event.key.toUpperCase())]
    if (option) setChosen(option.number)
    const level = LEVELS[['1', '2', '3'].indexOf(event.key)]
    if (level) setConfidence(level.confidence)
  })
  useEffect(() => {
    const listener = (event: KeyboardEvent) => onKey(event)
    document.addEventListener('keydown', listener)
    return () => document.removeEventListener('keydown', listener)
  }, [])

  const verdict = answered?.correction
    ? answered.correction.correct
    : grading?.status === 'done'
      ? grading.correct
      : null
  return (
    <>
      <div className="question-head">
        <span className="label">{asked.label}</span>
        {answered &&
          reveal &&
          verdict !== null &&
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
      <div className="statement">
        <h1 lang="en">{question.statement}</h1>
        <span className="label">{note ?? noteOf(question)}</span>
      </div>
      {problem && <Notice>{problem}</Notice>}
      {answered && reveal && (
        <Corrected
          question={question}
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
      {answered && !reveal && (
        <>
          <p>Réponse notée. Tu la vérifieras en lisant : la bonne réponse est dans le cours.</p>
          <div className="actions">
            <button type="button" className="button primary" disabled={busy} onClick={onNext}>
              {nextLabel}
            </button>
          </div>
        </>
      )}
      {!answered && (
        <>
          {open ? (
            <div className="answer-text">
              <label htmlFor="answer-text" className="label">
                Ta réponse
              </label>
              <textarea
                id="answer-text"
                className="field"
                rows={4}
                autoFocus
                placeholder="Explique avec tes mots…"
                value={text}
                readOnly={sent !== undefined || sending}
                onChange={(event) => setText(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key !== 'Enter' || event.shiftKey || event.nativeEvent.isComposing) {
                    return // Maj+Entrée goes to the line
                  }
                  event.preventDefault()
                  if (text.trim() === '' || sending) return
                  event.currentTarget.blur() // then 1, 2 or 3 for the confidence
                  if (ready) void validate()
                  else void send()
                }}
              />
              <span className="hint">
                {sent
                  ? 'Envoyée : Claude corrige pendant que tu choisis ta confiance.'
                  : 'Réponds sans regarder le cours. Entrée envoie ta réponse à Claude, Maj+Entrée va à la ligne.'}
              </span>
            </div>
          ) : written ? (
            <div className="answer-line">
              <label htmlFor="answer-line" className="label">
                {question.format === 'value' ? 'Ta valeur' : 'Ta réponse'}
              </label>
              <input
                id="answer-line"
                className={`field${question.format === 'value' ? ' mono' : ''}`}
                type="text"
                autoComplete="off"
                spellCheck={false}
                autoFocus
                placeholder={
                  question.format === 'value'
                    ? 'Un nombre, par exemple 2,5'
                    : 'Un mot ou une courte expression'
                }
                value={text}
                onChange={(event) => setText(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key !== 'Enter') return
                  event.preventDefault()
                  if (ready) void validate()
                  else if (given) event.currentTarget.blur() // then 1, 2 or 3
                }}
              />
              <span className="hint">
                Réponds sans regarder le cours. Entrée, puis 1, 2 ou 3 pour ta confiance.
              </span>
            </div>
          ) : (
            <div role="radiogroup" aria-label="Propositions" className="options">
              {question.options.map((option, index) => (
                <button
                  key={option.number}
                  type="button"
                  role="radio"
                  aria-checked={chosen === option.number}
                  className="option"
                  onClick={() => setChosen(option.number)}
                >
                  <span className="option-key">{LETTERS[index]}</span>
                  <span lang="en">{option.text}</span>
                </button>
              ))}
            </div>
          )}
          <div role="radiogroup" aria-labelledby="confidence-question" className="confidence">
            <span id="confidence-question" className="confidence-question">
              À quel point es-tu sûr de ta réponse ?
            </span>
            <div className="levels">
              {LEVELS.map((level, index) => (
                <button
                  key={level.confidence}
                  type="button"
                  role="radio"
                  aria-checked={confidence === level.confidence}
                  className="level"
                  onClick={() => setConfidence(level.confidence)}
                >
                  <span className="gauge" aria-hidden="true">
                    {[0, 1, 2].map((k) => (
                      <span key={k} className={k < level.dots ? 'on' : undefined} />
                    ))}
                  </span>
                  {level.name}
                  <span className="shortcut" aria-hidden="true">
                    {index + 1}
                  </span>
                </button>
              ))}
            </div>
          </div>
          <div className="actions">
            <button
              type="button"
              className="button primary"
              disabled={!ready || busy}
              onClick={() => void validate()}
            >
              Valider
            </button>
            {!sent && (
              <button
                type="button"
                className="button ghost"
                disabled={busy || sending}
                onClick={() =>
                  onAnswer({ chosen: null, text: null, confidence: null, gradingId: null })
                }
              >
                Je ne sais pas
              </button>
            )}
          </div>
        </>
      )}
    </>
  )
}

type CorrectedProps = {
  question: QuestionToAsk
  answered: Answered
  grading?: GradingState // an open answer: its grading by Claude, as last read
  late: boolean // Claude grades it still, after 15 s: the session goes on
  busy: boolean
  nextLabel: string
  onClaimed?: (answerId: number, claimId: number) => void
  onNext: () => void
  onShowCourse?: () => void
}

/** The correction: the options of an MCQ, or the answer written; the mistake made while
 *  sure (R10); what Claude says of an open answer (T6) or what was expected; the way
 *  on, and "Je pense avoir juste" for a value or a short answer found wrong (T5). While
 *  Claude grades an open answer, only the wait shows, 15 s at most. */
function Corrected({
  question,
  answered,
  grading,
  late,
  busy,
  nextLabel,
  onClaimed,
  onNext,
  onShowCourse,
}: CorrectedProps) {
  const { chosen, text, correction } = answered
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
        Claude corrige ta réponse…
      </p>
    )
  }
  const priority = correction?.priority ?? grading?.priority ?? false
  return (
    <>
      {question.format === 'mcq' && correction ? (
        <Options question={question} chosen={chosen} correction={correction} />
      ) : (
        <div className="given">
          <span className="label">Ta réponse</span>
          {text ?? 'Je ne sais pas'}
        </div>
      )}
      {priority && (
        <p className="priority">
          <strong>Tu étais sûr de toi.</strong> C'est le type d'erreur qu'on retient le mieux
          une fois corrigé : prends le temps de lire l'explication.
        </p>
      )}
      {grading && <ClaudeGrading grading={grading} />}
      {correction && question.format !== 'mcq' && (
        <div className="correction">
          <span className="label">Correction</span>
          {question.format === 'open' ? (
            <span lang="en">{correction.expected}</span>
          ) : (
            <span>
              Réponse attendue : <strong>{correction.expected}</strong>
            </span>
          )}
          {correction.explanation && <span>{correction.explanation}</span>}
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

/** The options of an MCQ after the answer: the right one and a wrong choice, with
 *  their explanation. */
function Options({
  question,
  chosen,
  correction,
}: {
  question: QuestionToAsk
  chosen: number | null
  correction: Correction
}) {
  return (
    <div className="options">
      {question.options.map((option, index) => {
        const right = option.number === correction.correct_option
        const wrong = option.number === chosen && !right
        return (
          <div
            key={option.number}
            className={`option result${right ? ' right' : ''}${wrong ? ' wrong' : ''}`}
          >
            <span className="option-key">{LETTERS[index]}</span>
            <span className="option-body">
              <span className="option-text" lang="en">
                {option.text}
              </span>
              {(right || wrong) && (
                <span className="option-explanation">
                  <strong>{right ? 'Bonne réponse.' : 'Ton choix.'}</strong>{' '}
                  {correction.explanations[option.number - 1]}
                </span>
              )}
            </span>
          </div>
        )
      })}
    </div>
  )
}

/** What Claude says of an open answer (T6): each criterion met or not, with its
 *  sentence, the comment, then the model answer. */
function ClaudeGrading({ grading }: { grading: GradingState }) {
  const by = grading.provisional ? 'le modèle local' : 'Claude'
  return (
    <>
      <GradingNotes grading={grading} />
      {grading.status === 'done' && (
        <CriteriaChecked grading={grading} title={`Critères vérifiés par ${by}`} />
      )}
      <div className="correction">
        <span className="label">Correction</span>
        <span lang="en">{grading.expected_answer}</span>
      </div>
    </>
  )
}

/** Where a grading by Claude stands when it is not plain: still on its way after 15 s,
 *  failed, or provisional, by the local model (T6). */
export function GradingNotes({ grading }: { grading: GradingState }) {
  return (
    <>
      {grading.status === 'pending' && (
        <p className="grading-wait" role="status">
          La correction prend plus de temps que prévu. Elle s'affichera à la fin, et ta
          réponse comptera dès qu'elle arrive.
        </p>
      )}
      {grading.status === 'failed' && (
        <p className="grading-wait" role="status">
          Claude n'a pas pu corriger ta réponse : elle n'est pas comptée, et la question
          reviendra.
        </p>
      )}
      {grading.status === 'done' && grading.provisional && (
        <p className="grading-wait" role="status">
          Correction provisoire du modèle local : Claude n'a pas pu corriger. Il la vérifiera
          à son retour, et ta réponse sera recorrigée s'il n'est pas d'accord.
        </p>
      )}
    </>
  )
}

/** The criteria of a grading, met or not, each with Claude's sentence, then its
 *  comment; `summary` above them, such as the points of an exercise. */
export function CriteriaChecked({
  grading,
  title,
  summary,
}: {
  grading: GradingState
  title: string
  summary?: string
}) {
  return (
    <div className="criteria">
      <span className="label">{title}</span>
      {summary && <span className="criteria-summary">{summary}</span>}
      <ul>
        {grading.criteria.map((result, index) => (
          <li key={index} className={result.met ? 'met' : 'missed'}>
            <span className="criterion-mark" aria-hidden="true">
              <Icon name={result.met ? 'check' : 'close'} size={12} />
            </span>
            <span className="criterion-body">
              <span className="visually-hidden">
                {result.met ? 'Rempli : ' : 'Non rempli : '}
              </span>
              <span lang="en">{result.criterion}</span>
              <span className="criterion-comment">{result.comment}</span>
            </span>
          </li>
        ))}
      </ul>
      {grading.comment && <p className="claude-comment">{grading.comment}</p>}
    </div>
  )
}
