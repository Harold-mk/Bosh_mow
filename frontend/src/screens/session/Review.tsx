import { useEffect, useState } from 'react'
import {
  type ClaimState,
  type GradingState,
  getClaim,
  getGrading,
  type QuestionToAsk,
} from '../../api.ts'
import { count } from '../../format.ts'
import type { Answered } from './QuestionCard.tsx'

/** An answer of the session, as the review at its end shows it. */
export type Result = {
  question: QuestionToAsk
  outcome: 'right' | 'wrong' | 'pending' | 'failed'
  priority: boolean // a mistake made while sure (R10)
  answerId: number | null // graded by the code: a value or a short answer can be claimed
  gradingId: number | null // an open answer, graded by Claude (T6)
  claimId: number | null // "Je pense avoir juste": Claude judges it in the background
  late: boolean // decided after its question was left: shown at the end
}

/** A result as the review lists it, with what Claude decided after the question. */
type Line = Result & { note: string | null }

const READ_EVERY_MS = 2000 // how often what Claude still decides is read

/** The result of an answer as it was validated. */
export function resultOf(question: QuestionToAsk, answered: Answered): Result {
  const { correction, grading } = answered
  const nothing = { answerId: null, gradingId: null, claimId: null, late: false }
  if (grading) return { question, ...nothing, ...outcomeOf(grading), gradingId: grading.id }
  return {
    question,
    ...nothing,
    outcome: correction?.correct ? 'right' : 'wrong',
    priority: correction?.priority ?? false,
    answerId: correction?.answer_id ?? null,
  }
}

/** What a grading says of its answer. */
function outcomeOf(grading: GradingState): Pick<Result, 'outcome' | 'priority'> {
  const outcome =
    grading.status === 'done' ? (grading.correct ? 'right' : 'wrong') : grading.status
  return { outcome, priority: grading.priority }
}

/** A grading that came after its answer was validated. */
export function withGrading(results: Result[], grading: GradingState): Result[] {
  return results.map((result) =>
    result.gradingId === grading.id ? { ...result, ...outcomeOf(grading) } : result,
  )
}

/** "Je pense avoir juste" on an answer: its claim is followed until the end. */
export function withClaim(results: Result[], answerId: number, claimId: number): Result[] {
  return results.map((result) => (result.answerId === answerId ? { ...result, claimId } : result))
}

/** Leaving a question: an answer that Claude still grades is shown at the end (T6). */
export function leaving(results: Result[]): Result[] {
  return results.map((result) =>
    result.outcome === 'pending' ? { ...result, late: true } : result,
  )
}

/** A result with what Claude decided once its question was left. */
function lineOf(result: Result, grading?: GradingState, claim?: ClaimState): Line {
  if (result.claimId !== null) {
    const status = claim?.status ?? 'pending'
    if (status === 'accepted') {
      const note = `Tu avais juste : Claude t'a donné raison. ${claim?.comment ?? ''}`
      return { ...result, outcome: 'right', late: true, note: note.trim() }
    }
    const note = {
      pending: 'Tu penses avoir juste : Claude examine ta réponse.',
      refused: `Claude maintient la correction. ${claim?.comment ?? ''}`.trim(),
      failed: "Claude n'a pas pu examiner ta réponse : la correction reste celle de l'app.",
    }[status]
    return { ...result, note }
  }
  if (!result.late) return { ...result, note: null }
  const line = grading ? { ...result, ...outcomeOf(grading) } : result
  // A grading of the local model is provisional until Claude checks it (D6).
  const by = grading?.provisional ? ' (provisoire, par le modèle local)' : ''
  const note = {
    right: `Juste${by} : ${grading?.comment ?? ''}`.trim(),
    wrong: `Corrigée après coup${by} : ${grading?.comment ?? ''}`.trim(),
    failed: "Claude n'a pas pu la corriger : elle n'est pas comptée, et la question reviendra.",
    pending: 'Claude la corrige encore : elle comptera dès que sa correction arrive.',
  }[line.outcome]
  return { ...line, note }
}

/** The end of a session: the questions to review, the mistakes made while sure first
 *  (R10), and what Claude decided after their question was left: the gradings of open
 *  answers that came late (T6), and the claims (T5). */
export function Review({ results }: { results: Result[] }) {
  const [gradings, setGradings] = useState<Record<number, GradingState>>({})
  const [claims, setClaims] = useState<Record<number, ClaimState>>({})
  const lateIds = results.flatMap((result) =>
    result.late && result.gradingId !== null ? [result.gradingId] : [],
  )
  const claimIds = results.flatMap((result) => (result.claimId !== null ? [result.claimId] : []))
  const followed = `${lateIds.join(',')}|${claimIds.join(',')}`

  // What Claude still decides is read, then read again until all of it is decided.
  useEffect(() => {
    if (lateIds.length + claimIds.length === 0) return
    let timer: ReturnType<typeof setTimeout> | undefined
    let stopped = false
    const readAll = () =>
      Promise.all([Promise.all(lateIds.map(getGrading)), Promise.all(claimIds.map(getClaim))]).then(
        ([gradingStates, claimStates]) => {
          if (stopped) return
          setGradings(Object.fromEntries(gradingStates.map((state) => [state.id, state])))
          setClaims(Object.fromEntries(claimStates.map((state) => [state.id, state])))
          const waiting = [...gradingStates, ...claimStates].some(
            (state) => state.status === 'pending',
          )
          if (waiting) timer = setTimeout(readAll, READ_EVERY_MS)
        },
        () => {
          if (!stopped) timer = setTimeout(readAll, READ_EVERY_MS) // read again later
        },
      )
    void readAll()
    return () => {
      stopped = true
      clearTimeout(timer)
    }
  }, [followed])

  const lines = results.map((result) =>
    lineOf(
      result,
      result.gradingId !== null ? gradings[result.gradingId] : undefined,
      result.claimId !== null ? claims[result.claimId] : undefined,
    ),
  )
  const wrong = lines
    .filter((line) => line.outcome === 'wrong')
    .sort((a, b) => Number(b.priority) - Number(a.priority))
  const after = lines.filter((line) => line.late && line.outcome !== 'wrong')
  if (wrong.length === 0 && after.length === 0) return null

  return (
    <div className="recap">
      {wrong.length > 0 && (
        <>
          <span className="label">À revoir · {count(wrong.length, 'question')}</span>
          <ul className="recap-list">
            {wrong.map((line, index) => (
              <li key={index}>
                <span lang="en">{line.question.statement}</span>
                {line.priority && (
                  <span className="recap-note sure">
                    Erreur faite en étant sûr : à relire en premier.
                  </span>
                )}
                {line.note && <span className="recap-note">{line.note}</span>}
              </li>
            ))}
          </ul>
        </>
      )}
      {after.length > 0 && (
        <>
          <span className="label">Corrections arrivées après coup</span>
          <ul className="recap-list">
            {after.map((line, index) => (
              <li key={index}>
                <span lang="en">{line.question.statement}</span>
                {line.note && <span className="recap-note">{line.note}</span>}
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  )
}
