/* The figures of a study session, as in backend/bosh_mow/study/queue.py. */

export const SESSION_SECONDS = 15 * 60 // the minimum session: the daily queue (R12)
const SECONDS_PER_QUESTION = 36

/** About how many minutes the daily queue takes: 15 at most. */
export function queueMinutes(questions: number): number {
  return Math.min(SESSION_SECONDS / 60, Math.ceil((questions * SECONDS_PER_QUESTION) / 60))
}

/** Whether a key goes to a field, or comes with Ctrl or Alt: shortcuts leave it alone. */
export function typing(event: KeyboardEvent): boolean {
  const target = event.target
  const inField =
    target instanceof HTMLElement && target.closest('input, textarea, select') !== null
  return inField || event.ctrlKey || event.altKey || event.metaKey
}
