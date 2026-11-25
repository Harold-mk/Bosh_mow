/* The figures of a study session, as in backend/bosh_mow/study/queue.py. */

export const SESSION_SECONDS = 15 * 60 // the minimum session: the daily queue (R12)
const SECONDS_PER_QUESTION = 36

/** About how many minutes the daily queue takes: 15 at most. */
export function queueMinutes(questions: number): number {
  return Math.min(SESSION_SECONDS / 60, Math.ceil((questions * SECONDS_PER_QUESTION) / 60))
}

/** Whether the shortcuts of a session leave a key alone: it goes to a field or to a
 *  window over the session, such as the reader, or comes with Ctrl or Alt. */
export function notForShortcuts(event: KeyboardEvent): boolean {
  const target = event.target
  const elsewhere =
    target instanceof HTMLElement &&
    target.closest('input, textarea, select, [role="dialog"]') !== null
  return elsewhere || event.ctrlKey || event.altKey || event.metaKey
}
