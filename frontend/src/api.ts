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
  format: 'mcq' | 'value' | 'short' | 'open' // the open answer is graded by Claude (T6)
  statement: string // in English (R5)
  options: OptionToAsk[] // an MCQ only
  tolerance: number | null // a value only: relative, 0.01 for 1 %
  subject: string
  resource_id: number // where its answer is (R4)
  first_page: number
  last_page: number
  exercise: ExerciseView | null // an exercise (T3), asked without confidence
}

/** An example worked step by step, to read before a solo problem (R14). */
export type WorkedExample = { statement: string; steps: string[] }

/** What an exercise shows before its answer (T3). */
export type ExerciseView = {
  kind: 'worked' | 'completion' | 'solo'
  topic: string // what the exercises of its notion practise, in English
  given: string[] // all the steps of a worked example, the first of a completion
  to_do: number // the steps left to the student
  worked_example: WorkedExample | null // in a review, while it is offered (R14)
}

/** The correction of an answer, given at once and without AI (T5). */
export type Correction = {
  correct: boolean
  priority: boolean // a mistake made while sure (R10)
  correct_option: number | null // an MCQ: the right option
  explanations: string[] // an MCQ: of each option, by number from 1, in French
  expected: string | null // a value, a short or an open answer: what was expected
  explanation: string | null // a value or a short answer: how to find it, in French
  answer_id: number // the answer saved, which "Je pense avoir juste" refers to
  solution: string[] // an exercise: every step of its solution
}

/** "Je pense avoir juste" (T5): Claude judges a value or a short answer again. */
export type ClaimState = {
  id: number
  answer_id: number
  status: 'pending' | 'accepted' | 'refused' | 'failed'
  comment: string | null // Claude's reason, in French
  detail: string | null // why it failed
}

/** A criterion of an open answer, met or not, with Claude's sentence about it (T6). */
export type CriterionResult = { criterion: string; met: boolean; comment: string }

/** Where the grading of an open answer by Claude stands (T6). */
export type GradingState = {
  id: number
  question_id: number
  status: 'pending' | 'done' | 'failed'
  correct: boolean | null // once done: every criterion met
  provisional: boolean // by the local model, until Claude checks it (D6)
  priority: boolean // a mistake made while sure (R10)
  criteria: CriterionResult[] // once done
  comment: string | null // once done, in French
  expected_answer: string // the model answer, in English
  detail: string | null // why it failed
  solution: string[] // an exercise: every step of its solution
  points: number | null // an exercise, once graded: the points earned…
  out_of: number | null // … out of those of its steps to do
  dropped_at: number | null // an exercise: its first step to do missed, from 1
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

/** Answer a question: an MCQ with `chosen_option`, a value or a short answer with
 *  `answer_text`; neither is "Je ne sais pas", without confidence. */
export function giveAnswer(
  sessionId: number,
  answer: {
    question_id: number
    chosen_option: number | null
    answer_text: string | null
    confidence: Confidence | null
    seconds: number
  },
): Promise<Correction> {
  return request('POST', `/sessions/${sessionId}/answers`, answer)
}

/** Send an open answer to Claude at once (T6): the grading runs while the confidence
 *  is chosen. */
export function sendOpenAnswer(
  sessionId: number,
  answer: {
    question_id: number
    answer_text: string
    seconds?: number // an exercise: its answer is given as it is sent, no confidence
  },
): Promise<{ id: number }> {
  return request('POST', `/sessions/${sessionId}/gradings`, answer)
}

/** The confidence in an open answer already sent (R6): it counts once graded. */
export function giveConfidence(
  gradingId: number,
  given: { confidence: Confidence; seconds: number },
): Promise<GradingState> {
  return request('POST', `/gradings/${gradingId}/confidence`, given)
}

export function getGrading(gradingId: number): Promise<GradingState> {
  return request('GET', `/gradings/${gradingId}`)
}

/** Je pense avoir juste: Claude judges the answer again, in the background. */
export function claimAnswer(answerId: number): Promise<{ id: number }> {
  return request('POST', `/answers/${answerId}/claim`)
}

export function getClaim(claimId: number): Promise<ClaimState> {
  return request('GET', `/claims/${claimId}`)
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

export function getNotion(notionId: number): Promise<NotionToStudy> {
  return request('GET', `/notions/${notionId}`)
}

/** A page of a notion, as it is read: with what it shows if mostly in images (T11). */
export type PageText = { number: number; text: string; description: string | null }

export function getNotionPages(notionId: number): Promise<PageText[]> {
  return request('GET', `/notions/${notionId}/pages`)
}

/** The study of a notion once started (R13), with its session. */
export type NotionSession = {
  session_id: number
  notion: NotionToStudy
  warmup: QuestionToAsk | null // a question already succeeded, first (R15)
  pretests: QuestionToAsk[] // before the reading, not scheduled
  tests: QuestionToAsk[] // after the reading: they enter the reviews
  exercises: QuestionToAsk[] // then: worked example, completion, solo problem (R14)
}

export function startNotion(notionId: number): Promise<NotionSession> {
  return request('POST', `/notions/${notionId}/session`)
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

/** An imported file with its subject, for the reader. */
export type ResourceView = {
  id: number
  subject_id: number
  file_name: string
  kind: 'pdf' | 'markdown'
  page_count: number // pages of a PDF, sections of a Markdown file
}

/** A title of the outline of a file; `page` is a PDF page or a Markdown section. */
export type Heading = { level: number; title: string; page: number }

export function getResource(resourceId: number): Promise<ResourceView> {
  return request('GET', `/resources/${resourceId}`)
}

export function getOutline(resourceId: number): Promise<Heading[]> {
  return request('GET', `/resources/${resourceId}/outline`)
}

/** Every page of a file as text: the reader shows a Markdown file so. */
export function getResourcePages(resourceId: number): Promise<PageText[]> {
  return request('GET', `/resources/${resourceId}/pages`)
}

/** Where a background task of Claude stands, and why it waits or failed. */
export type TaskState = {
  status: 'pending' | 'running' | 'done' | 'failed'
  error: string | null
}

/** A chapter in the list of its subject, with where its notions stand. */
export type ChapterSummary = {
  number: number
  title: string
  role: Role
  notions: number // validated
  studied: number
  preparation: TaskState['status'] | null // the proposal of its notions, until validated
}

/** A notion as Claude proposes it, before its title is checked (R3). */
export type ProposedNotion = {
  title: string
  summary: string
  resource_id: number
  first_page: number
  last_page: number
}

/** Where the proposal of the notions of a chapter stands (T1 pass 2). */
export type PreparationState = TaskState & {
  notions: ProposedNotion[] // once done
  boundary_alert: string | null // if the chapter seems to start or end at the wrong place
}

export type QuestionSummary = {
  id: number
  role: 'pretest' | 'review'
  format: 'mcq' | 'value' | 'short' | 'open'
  statement: string // in English (R5)
  reported: boolean // "Signaler": out of the reviews
}

/** An exercise of a notion (T3, R14): an example worked step by step, a problem to
 *  complete, or a problem to solve alone. */
export type ExerciseSummary = {
  id: number
  kind: 'worked' | 'completion' | 'solo'
  format: 'value' | 'open' // its result: a number, or a reasoning or code
  statement: string // in English (R5)
  reported: boolean // "Signaler": out of the reviews
}

/** Where the writing of the exercises of a notion stands (T3). */
export type ExercisesState = TaskState & {
  none_reason: string | null // done without exercises: why, in English
}

/** A validated notion, with its questions and exercises, and where their writing
 *  stands (T2, T3). */
export type Notion = {
  id: number
  number: number
  title: string
  summary: string
  resource_id: number
  first_page: number
  last_page: number
  studied: boolean
  questions: QuestionSummary[] // [] while Claude writes them
  writing: TaskState | null // null if never asked, as for the first proposals
  exercises: ExerciseSummary[] // [] while Claude writes them, or if none
  exercise_writing: ExercisesState | null // null if never asked
}

export type ChapterView = {
  id: number
  number: number
  title: string
  role: Role
  notions: Notion[] // [] until they are validated
}

export function listChapters(subjectId: number): Promise<ChapterSummary[]> {
  return request('GET', `/subjects/${subjectId}/chapters`)
}

export function getChapter(subjectId: number, number: number): Promise<ChapterView> {
  return request('GET', `/subjects/${subjectId}/chapters/${number}`)
}

/** Where the proposal of the notions of a chapter stands; null if never asked. */
export function getPreparation(subjectId: number, number: number): Promise<PreparationState | null> {
  return request('GET', `/subjects/${subjectId}/chapters/${number}/preparation`)
}

/** Préparer ce chapitre: ask Claude for its notions, or try again at once. */
export function askPreparation(subjectId: number, number: number): Promise<PreparationState> {
  return request('POST', `/subjects/${subjectId}/chapters/${number}/preparation`)
}

/** Save the notions proposed, with their titles as checked (R3): Claude then writes
 *  the questions of each one. */
export function validateNotions(
  subjectId: number,
  number: number,
  titles: string[],
): Promise<ChapterView> {
  return request('POST', `/subjects/${subjectId}/chapters/${number}/notions`, { titles })
}

/** Ask Claude again for the questions of a notion, after a failure. */
export function askQuestions(notionId: number): Promise<TaskState> {
  return request('POST', `/notions/${notionId}/questions`)
}

/** Ask Claude again for the exercises of a notion, after a failure (T3). */
export function askExercises(notionId: number): Promise<ExercisesState> {
  return request('POST', `/notions/${notionId}/exercises`)
}

/** Signaler: take a wrong question out of the reviews. */
export function reportQuestion(questionId: number): Promise<void> {
  return request('POST', `/questions/${questionId}/report`)
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
