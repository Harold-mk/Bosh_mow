/* How numbers and dates are written in the interface, in French. */

import type { Resource } from './api.ts'

const DAY = 24 * 60 * 60 * 1000

/** A duration in minutes: "30 min", "1 h", "1 h 30". */
export function duration(minutes: number): string {
  const hours = Math.floor(minutes / 60)
  const rest = minutes % 60
  if (hours === 0) return `${minutes} min`
  return rest ? `${hours} h ${rest}` : `${hours} h`
}

/** A count and its noun: "0 page", "1 page", "400 pages" (singular below 2, in French). */
export function count(n: number, singular: string, plural = `${singular}s`): string {
  return `${n} ${n < 2 ? singular : plural}`
}

/** A calendar date 'YYYY-MM-DD' as "15 janv.", with the year if it is not this one. */
export function shortDate(isoDate: string): string {
  return formatDate(isoDate, 'short')
}

/** A calendar date 'YYYY-MM-DD' as "15 janvier", with the year if it is not this one. */
export function longDate(isoDate: string): string {
  return formatDate(isoDate, 'long')
}

/** A day as "Mardi 25 novembre". */
export function dayLabel(moment: Date): string {
  const text = new Intl.DateTimeFormat('fr-FR', {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
  }).format(moment)
  return text.charAt(0).toUpperCase() + text.slice(1)
}

/** Whole days from today to a calendar date 'YYYY-MM-DD'; negative once it is past. */
export function daysUntil(isoDate: string): number {
  const now = new Date()
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate())
  return Math.round((localDate(isoDate).getTime() - today.getTime()) / DAY)
}

/** Where a range of pages is: "p. 12–14", "sections 2–3" in a Markdown file; with the
 *  name of the file first when `withFile` ("stats.pdf, p. 12–14"). */
export function pagesOf(
  file: Resource | undefined,
  first: number,
  last: number,
  withFile = false,
): string {
  const range = first === last ? `${first}` : `${first}–${last}`
  const pages =
    file?.kind === 'markdown'
      ? `${first === last ? 'section' : 'sections'} ${range}`
      : `p. ${range}`
  return withFile && file ? `${file.file_name}, ${pages}` : pages
}

/** "PDF · 400 pages" or "Markdown · 6 sections". */
export function fileSummary(resource: Resource): string {
  return resource.kind === 'pdf'
    ? `PDF · ${count(resource.page_count, 'page')}`
    : `Markdown · ${count(resource.page_count, 'section')}`
}

function formatDate(isoDate: string, month: 'short' | 'long'): string {
  const date = localDate(isoDate)
  const year = date.getFullYear() === new Date().getFullYear() ? undefined : 'numeric'
  return new Intl.DateTimeFormat('fr-FR', { day: 'numeric', month, year }).format(date)
}

/** Midnight of a calendar date, in local time (new Date('2027-01-15') would be UTC). */
function localDate(isoDate: string): Date {
  const [year, month, day] = isoDate.split('-').map(Number)
  return new Date(year, month - 1, day)
}
