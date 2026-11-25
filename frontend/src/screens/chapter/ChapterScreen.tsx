import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router'
import {
  askQuestions,
  type ChapterView,
  getChapter,
  getSubject,
  messageOf,
  type Notion,
  type QuestionSummary,
  reportQuestion,
  type Resource,
  type Subject,
} from '../../api.ts'
import { KeyFigure } from '../../components/KeyFigure.tsx'
import { Notice } from '../../components/Notice.tsx'
import { PageHeader } from '../../components/PageHeader.tsx'
import { count, pagesOf } from '../../format.ts'
import './ChapterScreen.css'
import { NotionsProposal } from './NotionsProposal.tsx'

const FOLLOW_MS = 3000 // how often to look again while Claude writes questions
const FORMATS = { mcq: 'QCM', value: 'Valeur', short: 'Réponse courte', open: 'Question ouverte' }

/** Chapitre: the notions of a chapter (R3) and their questions. Before the notions are
 *  validated, Claude's proposal; after, the writing of their questions (T2) and
 *  "Signaler". Mastery, reviews and the evaluation of the chapter come with their lots. */
export function ChapterScreen() {
  const params = useParams()
  const subjectId = Number(params.subjectId)
  const number = Number(params.number)
  const [subject, setSubject] = useState<Subject>()
  const [chapter, setChapter] = useState<ChapterView>()
  const [error, setError] = useState<string>()

  useEffect(() => {
    Promise.all([getSubject(subjectId), getChapter(subjectId, number)]).then(
      ([found, view]) => {
        setSubject(found)
        setChapter(view)
      },
      (reason: unknown) => setError(messageOf(reason)),
    )
  }, [subjectId, number])

  // While Claude writes questions, the page looks again every few seconds.
  const writing =
    chapter?.notions.some(
      (notion) => notion.writing?.status === 'pending' || notion.writing?.status === 'running',
    ) ?? false
  useEffect(() => {
    if (!writing) return
    const timer = window.setInterval(() => {
      // Only a follow-up: if a look fails, the next one tries again.
      getChapter(subjectId, number).then(setChapter, () => {})
    }, FOLLOW_MS)
    return () => window.clearInterval(timer)
  }, [writing, subjectId, number])

  const parents = [
    { label: 'Mes matières', to: '/matieres' },
    ...(subject ? [{ label: subject.name, to: `/matieres/${subjectId}` }] : []),
  ]
  if (error) {
    return (
      <>
        <PageHeader parents={parents} title="Chapitre" crumb={`Chapitre ${number}`} />
        <Notice>{error}</Notice>
      </>
    )
  }
  if (!subject || !chapter) return null
  // The next notion to study, once Claude has written its questions.
  const next = chapter.notions.find(
    (notion) => !notion.studied && notion.questions.some((question) => !question.reported),
  )
  const started = chapter.notions.some((notion) => notion.studied)
  return (
    <>
      <PageHeader
        parents={parents}
        title={chapter.title}
        crumb={`Chapitre ${number}`}
        action={
          next && (
            <Link to={`/notion/${next.id}`} className="button primary">
              {started ? 'Continuer' : 'Commencer'} : {chapter.number}.{next.number}{' '}
              {next.title}
            </Link>
          )
        }
      />
      {chapter.notions.length > 0 ? (
        <ChapterNotions
          subjectId={subjectId}
          chapter={chapter}
          files={subject.resources}
          onChange={setChapter}
        />
      ) : (
        <NotionsProposal
          subjectId={subjectId}
          chapter={chapter}
          files={subject.resources}
          onValidated={setChapter}
        />
      )}
    </>
  )
}

type Props = {
  subjectId: number
  chapter: ChapterView
  files: Resource[]
  onChange: (chapter: ChapterView) => void
}

/** The validated notions, then every question of the chapter with "Signaler". */
function ChapterNotions({ subjectId, chapter, files, onChange }: Props) {
  const [error, setError] = useState<string>()
  const { notions } = chapter
  const studied = notions.filter((notion) => notion.studied).length
  const next = notions.find((notion) => !notion.studied)
  const questions = notions.flatMap((notion) =>
    notion.questions.map((question) => ({ question, notion })),
  )
  const reported = questions.filter(({ question }) => question.reported).length
  const several = new Set(notions.map((notion) => notion.resource_id)).size > 1

  /** Do something, then show the chapter as it now is. */
  async function act(action: () => Promise<unknown>) {
    try {
      setError(undefined)
      await action()
      onChange(await getChapter(subjectId, chapter.number))
    } catch (reason) {
      setError(messageOf(reason))
    }
  }

  return (
    <>
      <div className="key-figures">
        <KeyFigure
          label="Notions"
          value={studied}
          unit={`/ ${notions.length}`}
          context={next ? `étudiées · prochaine : ${next.title}` : 'étudiées : tout le chapitre'}
        />
        <KeyFigure
          label="Questions"
          value={questions.length - reported}
          context={questionsContext(notions, reported)}
        />
      </div>
      {error && <Notice>{error}</Notice>}
      <section className="card chapter-section">
        <h2>Notions</h2>
        <ol className="chapter-list">
          {notions.map((notion) => {
            const failed = notion.questions.length === 0 && notion.writing?.status === 'failed'
            return (
              <li key={notion.id}>
                <span className="mono chapter-number">
                  {chapter.number}.{notion.number}
                </span>
                <span className="chapter-item">
                  <span className="chapter-item-title">{notion.title}</span>
                  <span className="hint">
                    {pagesOf(
                      files.find((file) => file.id === notion.resource_id),
                      notion.first_page,
                      notion.last_page,
                      several,
                    )}
                    {notion.questions.length > 0 &&
                      ` · ${count(notion.questions.filter((q) => !q.reported).length, 'question')}`}
                  </span>
                  {failed && (
                    <>
                      <span className="hint">L'écriture des questions a échoué.</span>
                      <details className="detail">
                        <summary>Détail</summary>
                        {notion.writing?.error}
                      </details>
                    </>
                  )}
                </span>
                {failed ? (
                  <button
                    type="button"
                    className="button secondary"
                    onClick={() => act(() => askQuestions(notion.id))}
                  >
                    Réessayer
                  </button>
                ) : (
                  <NotionStatus notion={notion} />
                )}
              </li>
            )
          })}
        </ol>
      </section>
      {questions.length > 0 && (
        <section className="card chapter-section">
          <h2>Questions du chapitre</h2>
          <p className="hint">
            Claude les écrit sans que tu les relises une à une : signale celles qui sont
            fausses, elles sortent des révisions. Pour l'instant, les séances posent les QCM ;
            les autres formats arrivent avec leur correction.
          </p>
          <ul className="question-list">
            {questions.map(({ question, notion }) => (
              <li key={question.id} className={question.reported ? 'reported' : undefined}>
                <span className="question-text">
                  <span lang="en">{question.statement}</span>
                  <span className="chips">
                    <span className="chip">
                      Notion {chapter.number}.{notion.number}
                    </span>
                    <span className="chip">{kind(question)}</span>
                  </span>
                </span>
                {question.reported ? (
                  <span className="hint">Signalée</span>
                ) : (
                  <button
                    type="button"
                    className="button ghost"
                    title="Retirer cette question des révisions"
                    onClick={() => act(() => reportQuestion(question.id))}
                  >
                    Signaler
                  </button>
                )}
              </li>
            ))}
          </ul>
        </section>
      )}
    </>
  )
}

/** Where a notion stands: its questions being written, then to study, then studied. */
function NotionStatus({ notion }: { notion: Notion }) {
  if (notion.questions.length > 0) {
    return notion.studied ? (
      <span className="notion-status">Étudiée</span>
    ) : (
      <span className="notion-status next">À étudier</span>
    )
  }
  const { writing } = notion
  if (writing?.status === 'pending' && writing.error) {
    return <span className="notion-status">En attente de Claude</span>
  }
  if (writing) return <span className="notion-status">Questions en cours d'écriture</span>
  return <span className="notion-status">Sans questions</span>
}

/** One line under the number of questions. */
function questionsContext(notions: Notion[], reported: number): string {
  const waiting = notions.filter((n) => n.questions.length === 0 && n.writing?.status !== 'failed')
  const failed = notions.filter((n) => n.questions.length === 0 && n.writing?.status === 'failed')
  if (waiting.length > 0) return `Claude écrit encore celles de ${count(waiting.length, 'notion')}`
  if (failed.length > 0) return `${count(failed.length, 'notion')} sans questions : à redemander`
  if (reported > 0) {
    return `${count(reported, 'question signalée', 'questions signalées')}, hors des révisions`
  }
  return 'écrites par Claude, 7 par notion'
}

function kind(question: QuestionSummary): string {
  return question.role === 'pretest' ? 'Prétest' : FORMATS[question.format]
}
