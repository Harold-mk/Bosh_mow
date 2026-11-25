import { Fragment, lazy, Suspense, useEffect, useState } from 'react'
import {
  getOutline,
  getResource,
  getSubject,
  type Heading,
  messageOf,
  type ResourceView,
  type Subject,
} from '../../api.ts'
import { Icon } from '../../components/Icon.tsx'
import { Notice } from '../../components/Notice.tsx'
import { fileSummary } from '../../format.ts'
import type { Target } from './pageScroll.ts'
import './Reader.css'
import { TextPages } from './TextPages.tsx'

// PDF.js weighs as much as the rest of the app: loaded when a PDF is opened.
const PdfPages = lazy(() => import('./PdfPages.tsx'))

const ZOOM = { least: 80, most: 150, step: 10 } // in % of the width of the reader

type Props = {
  resourceId: number
  page?: number // where it opens: a page of a PDF, a section of a Markdown file
  back?: { label: string; onClick: () => void } // over a session: the way back to it
}

/** Lecteur: a file as it is (R4), its outline and its pages, under a bar that always
 *  says where the reading is. Highlights, the assistant and the questions at the end
 *  of a section come with lot 6. */
export function Reader({ resourceId, page = 1, back }: Props) {
  const [shown, setShown] = useState(resourceId) // another file of the subject can be read
  const [file, setFile] = useState<ResourceView>()
  const [subject, setSubject] = useState<Subject>()
  const [outline, setOutline] = useState<Heading[]>([])
  const [current, setCurrent] = useState(page)
  const [target, setTarget] = useState<Target>({ page, at: 0 })
  const [zoom, setZoom] = useState(100)
  const [menu, setMenu] = useState<'outline' | 'files'>()
  const [error, setError] = useState<string>()

  useEffect(() => {
    let stopped = false
    getResource(shown)
      .then((found) => Promise.all([found, getSubject(found.subject_id), getOutline(found.id)]))
      .then(
        ([found, owner, headings]) => {
          if (stopped) return
          setFile(found)
          setSubject(owner)
          setOutline(headings)
        },
        (reason: unknown) => {
          if (!stopped) setError(messageOf(reason))
        },
      )
    return () => {
      stopped = true
    }
  }, [shown])

  function go(to: number) {
    if (!file) return
    const page = Math.min(Math.max(to, 1), file.page_count)
    setCurrent(page)
    setTarget({ page, at: Date.now() })
    setMenu(undefined)
  }

  function zoomBy(step: number) {
    setZoom((value) => Math.min(ZOOM.most, Math.max(ZOOM.least, value + step)))
    setTarget({ page: current, at: Date.now() }) // the page being read stays in view
  }

  function read(other: number) {
    setMenu(undefined)
    if (other === shown) return
    setFile(undefined)
    setShown(other)
    setCurrent(1)
    setTarget({ page: 1, at: Date.now() })
  }

  const pdf = file?.kind !== 'markdown'
  const chapter = subject?.chapters.findIndex((one) =>
    one.sources.some(
      (source) =>
        source.resource_id === shown && source.first_page <= current && current <= source.last_page,
    ),
  )
  const heading = outline.findLast((one) => one.page <= current)
  const where =
    subject && chapter !== undefined && chapter >= 0
      ? `Chapitre ${chapter + 1} · ${subject.chapters[chapter].title}`
      : (heading?.title ?? '')
  const previous = pdf ? 'Page précédente' : 'Section précédente'
  const next = pdf ? 'Page suivante' : 'Section suivante'

  return (
    <div className="reader">
      <div role="toolbar" aria-label="Outils de lecture" className="reader-toolbar">
        <button
          type="button"
          className="tool"
          aria-label="Sommaire"
          aria-expanded={menu === 'outline'}
          onClick={() => setMenu(menu === 'outline' ? undefined : 'outline')}
        >
          <Icon name="outline" />
        </button>
        <button
          type="button"
          className="reader-file"
          aria-label="Changer de document"
          aria-expanded={menu === 'files'}
          onClick={() => setMenu(menu === 'files' ? undefined : 'files')}
        >
          <span className="reader-file-text">
            <span className="label">
              {file ? `${pdf ? 'PDF' : 'Markdown'} · ${file.file_name}` : 'Document'}
            </span>
            {where && <span className="reader-where">{where}</span>}
          </span>
          <Icon name="down" size={16} />
        </button>
        <div className="reader-tools">
          <button
            type="button"
            className="tool"
            aria-label={previous}
            title={previous}
            disabled={!file || current <= 1}
            onClick={() => go(current - 1)}
          >
            <Icon name="previous" />
          </button>
          <span className="reader-position">
            {!pdf && <span className="label">Section</span>}
            <span className="mono">{current}</span>
            <span className="mono reader-total">/ {file?.page_count ?? '…'}</span>
          </span>
          <button
            type="button"
            className="tool"
            aria-label={next}
            title={next}
            disabled={!file || current >= file.page_count}
            onClick={() => go(current + 1)}
          >
            <Icon name="next" />
          </button>
          <span className="tool-separator" />
          <button
            type="button"
            className="tool"
            aria-label="Réduire"
            title="Réduire"
            disabled={zoom <= ZOOM.least}
            onClick={() => zoomBy(-ZOOM.step)}
          >
            <Icon name="minus" />
          </button>
          <span className="mono reader-zoom">{zoom} %</span>
          <button
            type="button"
            className="tool"
            aria-label="Agrandir"
            title="Agrandir"
            disabled={zoom >= ZOOM.most}
            onClick={() => zoomBy(ZOOM.step)}
          >
            <Icon name="plus" />
          </button>
          {back && (
            <>
              <span className="tool-separator" />
              <button type="button" className="button ghost" onClick={back.onClick}>
                {back.label}
              </button>
            </>
          )}
        </div>
        {menu === 'outline' && (
          <Outline title={file?.file_name ?? ''} headings={outline} here={heading} onGo={go} />
        )}
        {menu === 'files' && subject && <Files subject={subject} shown={shown} onRead={read} />}
      </div>
      {error && <Notice>{error}</Notice>}
      {/* A click in the pages closes the window open under the bar. */}
      <div className="reader-body" onMouseDown={() => setMenu(undefined)}>
        {file &&
          (pdf ? (
            <Suspense fallback={<p className="hint">Chargement du lecteur…</p>}>
              <PdfPages
                key={file.id}
                url={`/api/resources/${file.id}/file`}
                zoom={zoom}
                target={target}
                onPage={setCurrent}
              />
            </Suspense>
          ) : (
            <TextPages
              key={file.id}
              resourceId={file.id}
              zoom={zoom}
              target={target}
              onPage={setCurrent}
            />
          ))}
      </div>
    </div>
  )
}

type OutlineProps = {
  title: string
  headings: Heading[]
  here: Heading | undefined // the section being read
  onGo: (page: number) => void
}

/** The outline of the file: its first titles, each one unfolding the titles under it. */
function Outline({ title, headings, here, onGo }: OutlineProps) {
  const top = Math.min(...headings.map((heading) => heading.level))
  const groups: { heading: Heading; children: Heading[] }[] = []
  for (const heading of headings) {
    if (heading.level === top || groups.length === 0) groups.push({ heading, children: [] })
    else groups[groups.length - 1].children.push(heading)
  }
  // The group of the section being read starts unfolded.
  const [open, setOpen] = useState<ReadonlySet<number>>(
    () =>
      new Set(
        groups
          .map((group, k) =>
            group.heading === here || (here && group.children.includes(here)) ? k : -1,
          )
          .filter((k) => k >= 0),
      ),
  )

  function toggle(k: number) {
    const next = new Set(open)
    if (next.has(k)) next.delete(k)
    else next.add(k)
    setOpen(next)
  }

  return (
    <div role="dialog" aria-label="Sommaire" className="reader-menu">
      <div className="label reader-menu-title">Sommaire · {title}</div>
      {headings.length === 0 && (
        <p className="hint reader-menu-empty">
          Ce document n'a pas de sommaire : avance page par page.
        </p>
      )}
      {groups.map((group, k) => (
        <Fragment key={k}>
          <OutlineRow
            heading={group.heading}
            top
            here={here}
            open={group.children.length > 0 ? open.has(k) : undefined}
            onToggle={() => toggle(k)}
            onGo={onGo}
          />
          {open.has(k) &&
            group.children.map((child, j) => (
              <OutlineRow key={j} heading={child} here={here} onGo={onGo} />
            ))}
        </Fragment>
      ))}
    </div>
  )
}

type RowProps = {
  heading: Heading
  top?: boolean
  here: Heading | undefined
  open?: boolean // undefined: nothing under it to unfold
  onToggle?: () => void
  onGo: (page: number) => void
}

function OutlineRow({ heading, top = false, here, open, onToggle, onGo }: RowProps) {
  const classes = ['outline-row', top ? 'top' : 'child', heading === here ? 'current' : '']
  return (
    <div className={classes.join(' ').trim()}>
      <span>
        {open !== undefined && (
          <button
            type="button"
            className="outline-toggle"
            aria-label={`${open ? 'Replier' : 'Déplier'} ${heading.title}`}
            aria-expanded={open}
            onClick={onToggle}
          >
            <Icon name="next" size={16} />
          </button>
        )}
      </span>
      <button type="button" className="outline-title" onClick={() => onGo(heading.page)}>
        {heading.title}
      </button>
      <span className="outline-page">{heading.page}</span>
      <span className="outline-marker" />
    </div>
  )
}

type FilesProps = { subject: Subject; shown: number; onRead: (resourceId: number) => void }

/** The files of the subject: another one is read in a click. */
function Files({ subject, shown, onRead }: FilesProps) {
  return (
    <div role="dialog" aria-label="Documents de la matière" className="reader-menu files">
      <div className="label reader-menu-title">Documents · {subject.name}</div>
      {subject.resources.map((resource) => (
        <button
          key={resource.id}
          type="button"
          className={`file-row${resource.id === shown ? ' current' : ''}`}
          onClick={() => onRead(resource.id)}
        >
          <span className="file-row-text">
            <span className="file-row-name">{resource.file_name}</span>
            <span className="hint">{fileSummary(resource)}</span>
          </span>
          <span className="outline-marker" />
        </button>
      ))}
    </div>
  )
}
