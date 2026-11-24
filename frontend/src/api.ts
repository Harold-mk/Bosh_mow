/* Typed calls to the local API (backend/bosh_mow/api.py). A failed call throws an
   Error whose message can be shown as it is: the server explains in French what went
   wrong. */

export type Settings = {
  weekday_minutes: number
  weekend_minutes: number
  plan_if: string
  plan_then: string
  sidebar_collapsed: boolean
}

export type Role = 'core' | 'secondary'

/** The pages of one imported file that a chapter covers. */
export type ChapterSource = { resource_id: number; first_page: number; last_page: number }

/** A chapter; `objectives` are positions (from 1) in the objectives of its subject. */
export type Chapter = {
  title: string
  role: Role
  sources: ChapterSource[]
  objectives: number[]
}

/** An imported file. For a Markdown file, a page is a section. */
export type Resource = {
  id: number
  file_name: string
  kind: 'pdf' | 'markdown'
  page_count: number
}

export type Subject = {
  id: number
  name: string
  exam_date: string // YYYY-MM-DD
  status: 'draft' | 'active' | 'archived'
  objectives: string[]
  chapters: Chapter[]
  resources: Resource[]
  glossary: string[]
}

/** One line of Mes matières. */
export type SubjectSummary = {
  id: number
  name: string
  exam_date: string // YYYY-MM-DD
  chapter_count: number
  resource_count: number
}

/** Objectives, chapters and glossary, as the student reviews and validates them. */
export type Proposal = { objectives: string[]; chapters: Chapter[]; glossary: string[] }

/** Where the proposal of Claude for a subject stands. */
export type ProposalState = {
  status: 'pending' | 'running' | 'done' | 'failed'
  error: string | null // why Claude is awaited, or why the proposal failed
  proposal: Proposal | null // once done
}

export function getSettings(): Promise<Settings | null> {
  return request('GET', '/settings')
}

export function saveSettings(settings: Settings): Promise<Settings> {
  return request('PUT', '/settings', settings)
}

export function listSubjects(): Promise<SubjectSummary[]> {
  return request('GET', '/subjects')
}

export function getSubject(subjectId: number): Promise<Subject> {
  return request('GET', `/subjects/${subjectId}`)
}

/** Start a subject as a draft, hidden until it is validated. */
export function createSubject(name: string, examDate: string): Promise<Subject> {
  return request('POST', '/subjects', { name, exam_date: examDate })
}

/** The subject left being created, to take it up again; null if there is none. */
export function getDraft(): Promise<Subject | null> {
  return request('GET', '/draft')
}

/** Change the name or the exam date of a subject still being created. */
export function updateDraft(subjectId: number, name: string, examDate: string): Promise<Subject> {
  return request('PUT', `/subjects/${subjectId}`, { name, exam_date: examDate })
}

export function addFile(subjectId: number, file: File): Promise<Resource> {
  const form = new FormData()
  form.append('file', file)
  return request('POST', `/subjects/${subjectId}/files`, form)
}

export function deleteFile(subjectId: number, fileId: number): Promise<void> {
  return request('DELETE', `/subjects/${subjectId}/files/${fileId}`)
}

/** Ask Claude for objectives and chapters, in the background (T1). */
export function askProposal(subjectId: number): Promise<ProposalState> {
  return request('POST', `/subjects/${subjectId}/proposal`)
}

/** Where the proposal stands; null if none was asked for. */
export function getProposal(subjectId: number): Promise<ProposalState | null> {
  return request('GET', `/subjects/${subjectId}/proposal`)
}

/** Save the objectives and chapters as corrected by the student (R2, R3). */
export function validateSubject(subjectId: number, proposal: Proposal): Promise<Subject> {
  return request('POST', `/subjects/${subjectId}/validate`, proposal)
}

/** The message to show for an error caught from a call. */
export function messageOf(error: unknown): string {
  return error instanceof Error ? error.message : String(error)
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const init: RequestInit = { method }
  if (body instanceof FormData) {
    init.body = body
  } else if (body !== undefined) {
    init.body = JSON.stringify(body)
    init.headers = { 'Content-Type': 'application/json' }
  }
  let response: Response
  try {
    response = await fetch(`/api${path}`, init)
  } catch {
    throw new Error('Le serveur local ne répond pas.')
  }
  if (!response.ok) {
    throw new Error(await reasonOf(response))
  }
  return response.status === 204 ? (undefined as T) : ((await response.json()) as T)
}

/** The reason given by the server, which answers {"detail": "…"} for an error. */
async function reasonOf(response: Response): Promise<string> {
  try {
    const { detail } = (await response.json()) as { detail?: unknown }
    if (typeof detail === 'string') return detail
  } catch {
    // not JSON: fall through to the generic message
  }
  return `Erreur inattendue du serveur (${response.status}).`
}
