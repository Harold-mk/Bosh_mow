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

/** For one PDF file: its pages mostly in images, and how many are described (T11). */
export type DescriptionCount = { resource_id: number; to_describe: number; described: number }

/** Where the proposal of Claude for a subject stands. */
export type ProposalState = {
  status: 'pending' | 'running' | 'done' | 'failed'
  error: string | null // why Claude is awaited, or why the proposal failed
  proposal: Proposal | null // once done
}

/** Where the day stands, for the home screen and the sidebar. */
export type Today = {
  due: number // the questions of today's queue: never a backlog (R12, R27)
  successful_days: number // R26
  minimum_done: boolean
  missed_yesterday: boolean // warn before a second missed day in a row
  after_absence: boolean // today, the minimum session alone (R27)
  minutes: number // studied today
}

export function getToday(): Promise<Today> {
  return request('GET', '/today')
}

/** How sure the student is of an answer, given before validating it (R6). */
export type Confidence = 'sure' | 'hesitant' | 'guess'

/** An option as it is asked; its number in the question goes back with the answer. */
export type OptionToAsk = { number: number; text: string }

/** A question as it is asked: without its correction, its options in a random order. */
export type QuestionToAsk = {
  id: number
  role: 'pretest' | 'review'
  statement: string // in English (R5)
  options: OptionToAsk[]
  subject: string
  resource_id: number // where its answer is (R4)
  first_page: number
  last_page: number
}

/** The correction of an answer, given at once and without AI (T5). */
export type Correction = {
  correct: boolean
  correct_option: number
  explanations: string[] // of each option, by number from 1, in French
  priority: boolean // a mistake made while sure (R10)
}

/** A thought put aside during a session, to plan or drop before its end (R17). */
export type Thought = { id: number; text: string }

/** The next notion to study, in the subject with the closest exam. */
export type NotionToStudy = {
  id: number
  title: string
  summary: string
  subject: string
  chapter: string
  resource_id: number
  first_page: number
  last_page: number
}

/** Start the daily queue: the session, and how many questions it has. */
export function startQueue(): Promise<{ id: number; planned: number }> {
  return request('POST', '/sessions')
}

/** The next question of the daily queue; null once it is empty. */
export function nextQuestion(sessionId: number): Promise<QuestionToAsk | null> {
  return request('GET', `/sessions/${sessionId}/next`)
}

/** Answer a question: `chosen_option` null is "Je ne sais pas", without confidence. */
export function giveAnswer(
  sessionId: number,
  answer: {
    question_id: number
    chosen_option: number | null
    confidence: Confidence | null
    seconds: number
  },
): Promise<Correction> {
  return request('POST', `/sessions/${sessionId}/answers`, answer)
}

/** End a session, once its thoughts are sorted (R17): whether the day is successful. */
export function endSession(
  sessionId: number,
  completed: boolean,
): Promise<{ minimum_done: boolean }> {
  return request('POST', `/sessions/${sessionId}/end`, { completed })
}

/** Put a thought aside without leaving the question (key P, R17). */
export function noteThought(sessionId: number, text: string): Promise<Thought> {
  return request('POST', `/sessions/${sessionId}/thoughts`, { text })
}

/** The thoughts of a session still to plan or drop. */
export function getThoughts(sessionId: number): Promise<Thought[]> {
  return request('GET', `/sessions/${sessionId}/thoughts`)
}

/** Plan a thought at a local date and time 'YYYY-MM-DDTHH:MM', or drop it (null). */
export function decideThought(thoughtId: number, plannedFor: string | null): Promise<void> {
  return request('POST', `/thoughts/${thoughtId}/decision`, { planned_for: plannedFor })
}

/** J'ai décroché: counted, and the session goes on (R18). */
export function noteWandering(sessionId: number, questionId: number | null): Promise<void> {
  return request('POST', `/sessions/${sessionId}/wanderings`, { question_id: questionId })
}

/** The next notion to study; null if no validated notion has its questions yet. */
export function getNextNotion(): Promise<NotionToStudy | null> {
  return request('GET', '/notions/next')
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

/** How far the description of the pages mostly in images is, file by file. */
export function getDescriptions(subjectId: number): Promise<DescriptionCount[]> {
  return request('GET', `/subjects/${subjectId}/descriptions`)
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
