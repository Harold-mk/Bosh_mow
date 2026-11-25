import { useEffect, useState } from 'react'
import { type GradingState, getGrading, type QuestionToAsk } from '../../api.ts'
import { count } from '../../format.ts'
import type { Answered } from './QuestionCard.tsx'

/** An answer of the session, as the review at its end shows it. */
export type Result = {
  question: QuestionToAsk
  outcome: 'right' | 'wrong' | 'pending' | 'failed'
  priority: boolean // a mistake made while sure (R10)
  gradingId: number | null // an open answer, graded by Claude (T6)
  late: boolean // its question was left before its grading came: shown at the end
}

const READ_EVERY_MS = 2000 // how often the gradings still on their way are read

/** The result of an answer as it was validated. */
export function resultOf(question: QuestionToAsk, answered: Answered): Result {
  const { correction, grading } = answered
  if (grading) return { question, ...outcomeOf(grading), gradingId: grading.id, late: false }
  return {
    question,
    outcome: correction?.correct ? 'right' : 'wrong',
    priority: correction?.priority ?? false,
    gradingId: null,
    late: false,
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

/** Leaving a question: an answer that Claude still grades is shown at the end (T6). */
export function leaving(results: Result[]): Result[] {
  return results.map((result) =>
    result.outcome === 'pending' ? { ...result, late: true } : result,
  )
}

/** The end of a session: the questions to review, the mistakes made while sure first
 *  (R10), and the gradings that came after their question was left (T6). */
export function Review({ results }: { results: Result[] }) {
  const [read, setRead] = useState<Record<number, GradingState>>({})
  const late = results.flatMap((result) =>
    result.late && result.gradingId !== null ? [result.gradingId] : [],
  )
  const lateIds = late.join(',')

  // The late gradings are read, then read again while one of them is on its way.
  useEffect(() => {
    if (late.length === 0) return
    let timer: ReturnType<typeof setTimeout> | undefined
    let stopped = false
    const readAll = () =>
      Promise.all(late.map(getGrading)).then(
        (states) => {
          if (stopped) return
          setRead(Object.fromEntries(states.map((state) => [state.id, state])))
          if (states.some((state) => state.status === 'pending')) {
            timer = setTimeout(readAll, READ_EVERY_MS)
          }
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
  }, [lateIds])

  const final = results.map((result) => {
    const grading = result.gradingId !== null ? read[result.gradingId] : undefined
    return grading ? { ...result, ...outcomeOf(grading), grading } : { ...result, grading }
  })
  const wrong = final
    .filter((result) => result.outcome === 'wrong')
    .sort((a, b) => Number(b.priority) - Number(a.priority))
  const lateOthers = final.filter((result) => result.late && result.outcome !== 'wrong')
  if (wrong.length === 0 && lateOthers.length === 0) return null

  return (
    <div className="recap">
      {wrong.length > 0 && (
        <>
          <span className="label">À revoir · {count(wrong.length, 'question')}</span>
          <ul className="recap-list">
            {wrong.map((result, index) => (
              <li key={index}>
                <span lang="en">{result.question.statement}</span>
                {result.priority && (
                  <span className="recap-note sure">
                    Erreur faite en étant sûr : à relire en premier.
                  </span>
                )}
                {result.late && result.grading?.comment && (
                  <span className="recap-note">
                    Corrigée après coup : {result.grading.comment}
                  </span>
                )}
              </li>
            ))}
          </ul>
        </>
      )}
      {lateOthers.length > 0 && (
        <>
          <span className="label">Corrections arrivées après coup</span>
          <ul className="recap-list">
            {lateOthers.map((result, index) => (
              <li key={index}>
                <span lang="en">{result.question.statement}</span>
                <span className="recap-note">
                  {result.outcome === 'right'
                    ? `Juste : ${result.grading?.comment ?? ''}`
                    : result.outcome === 'failed'
                      ? "Claude n'a pas pu la corriger : elle n'est pas comptée, et la question reviendra."
                      : 'Claude la corrige encore : elle comptera dès que sa correction arrive.'}
                </span>
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  )
}
