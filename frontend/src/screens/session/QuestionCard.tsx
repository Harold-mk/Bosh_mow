import { useEffect, useEffectEvent, useState } from 'react'
import type { Confidence, Correction, QuestionToAsk } from '../../api.ts'
import { Icon } from '../../components/Icon.tsx'
import { notForShortcuts } from '../../study.ts'

/** A question on screen, with the label of its place in the queue. */
export type Asked = { question: QuestionToAsk; label: string; shownAt: number }

/** The answer given, an option or the text of a value or a short answer (both null:
 *  "Je ne sais pas"), and the correction it got. */
export type Answered = { chosen: number | null; text: string | null; correction: Correction }

type Props = {
  asked: Asked
  answered?: Answered // once validated
  reveal?: boolean // false for a pretest: noted, its correction waits for the reading
  note?: string // under the statement: the format and how it is corrected
  busy: boolean
  nextLabel: string
  onAnswer: (chosen: number | null, text: string | null, confidence: Confidence | null) => void
  onNext: () => void
  onShowCourse?: () => void // Voir le cours: its pages in the reader (R4)
}

const LETTERS = ['A', 'B', 'C', 'D']
const LEVELS: { confidence: Confidence; name: string; dots: number }[] = [
  { confidence: 'sure', name: 'Sûr', dots: 3 },
  { confidence: 'hesitant', name: 'Hésitant', dots: 2 },
  { confidence: 'guess', name: 'Au hasard', dots: 1 },
]

/** Under the statement: the format of the question and how it is corrected (T5). */
function noteOf(question: QuestionToAsk): string {
  if (question.format === 'value') {
    const percent = ((question.tolerance ?? 0.01) * 100).toLocaleString('fr-FR', {
      maximumFractionDigits: 2,
    })
    return `Valeur · corrigée instantanément, à ${percent} % près`
  }
  if (question.format === 'short') return 'Réponse courte · corrigée instantanément'
  return 'QCM · corrigé instantanément'
}

/** A question of the queue: its options or its field, and the confidence (R6), then its
 *  correction (T5). Keys: A to D for an option, 1 to 3 for the confidence, Entrée to go
 *  on. In the field of a value or a short answer, Entrée leaves it for the confidence. */
export function QuestionCard({
  asked,
  answered,
  reveal = true,
  note,
  busy,
  nextLabel,
  onAnswer,
  onNext,
  onShowCourse,
}: Props) {
  const [chosen, setChosen] = useState<number>()
  const [text, setText] = useState('')
  const [confidence, setConfidence] = useState<Confidence>()
  const { question } = asked
  const written = question.format !== 'mcq' // a value or a short answer, in a field
  const given = written ? text.trim() !== '' : chosen !== undefined
  const ready = given && confidence !== undefined

  const validate = () => {
    if (!ready) return
    onAnswer(written ? null : (chosen ?? null), written ? text.trim() : null, confidence)
  }

  const onKey = useEffectEvent((event: KeyboardEvent) => {
    if (notForShortcuts(event) || busy) return
    if (event.key === 'Enter') {
      // A button pressed with Entrée does its own action; an option or a level does not.
      const target = event.target
      if (target instanceof HTMLButtonElement && target.getAttribute('role') !== 'radio') return
      event.preventDefault()
      if (answered) onNext()
      else validate()
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

  return (
    <>
      <div className="question-head">
        <span className="label">{asked.label}</span>
        {answered &&
          reveal &&
          (answered.correction.correct ? (
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
      {answered && reveal && (
        <Corrected
          question={question}
          answered={answered}
          busy={busy}
          nextLabel={nextLabel}
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
          {written ? (
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
                  if (ready) validate()
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
              onClick={validate}
            >
              Valider
            </button>
            <button
              type="button"
              className="button ghost"
              disabled={busy}
              onClick={() => onAnswer(null, null, null)}
            >
              Je ne sais pas
            </button>
          </div>
        </>
      )}
    </>
  )
}

type CorrectedProps = {
  question: QuestionToAsk
  answered: Answered
  busy: boolean
  nextLabel: string
  onNext: () => void
  onShowCourse?: () => void
}

/** The correction: the options of an MCQ, the right one and a wrong choice with their
 *  explanation; or the answer written, then what was expected and why. Then the mistake
 *  made while sure (R10), and the way on. */
function Corrected({
  question,
  answered,
  busy,
  nextLabel,
  onNext,
  onShowCourse,
}: CorrectedProps) {
  const { chosen, text, correction } = answered
  return (
    <>
      {question.format === 'mcq' ? (
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
      ) : (
        <div className="given">
          <span className="label">Ta réponse</span>
          {text ?? 'Je ne sais pas'}
        </div>
      )}
      {correction.priority && (
        <p className="priority">
          <strong>Tu étais sûr de toi.</strong> C'est le type d'erreur qu'on retient le mieux
          une fois corrigé : prends le temps de lire l'explication.
        </p>
      )}
      {question.format !== 'mcq' && (
        <div className="correction">
          <span className="label">Correction</span>
          <span>
            Réponse attendue : <strong>{correction.expected}</strong>
          </span>
          {correction.explanation && <span>{correction.explanation}</span>}
        </div>
      )}
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
    </>
  )
}
