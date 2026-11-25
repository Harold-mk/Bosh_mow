import {
  getDocument,
  GlobalWorkerOptions,
  type PDFDocumentProxy,
  type RenderTask,
} from 'pdfjs-dist'
import workerUrl from 'pdfjs-dist/build/pdf.worker.min.mjs?url'
import { useEffect, useRef, useState } from 'react'
import { messageOf } from '../../api.ts'
import { Notice } from '../../components/Notice.tsx'
import { type PagesProps, usePageScroll } from './pageScroll.ts'

// PDF.js is loaded with this module, when a PDF is opened: not with the app.
GlobalWorkerOptions.workerSrc = workerUrl

const WIDEST = 860 // px: a page at 100 % fills the reader up to this width
const NEAR = '150% 0px' // pages drawn: those within a screen and a half of the view

/** The pages of a PDF as they are (R4), one after the other: each one is drawn when it
 *  comes near the view and let go when it leaves, so that a long book stays light. */
export default function PdfPages({ url, zoom, target, onPage }: PagesProps & { url: string }) {
  const box = useRef<HTMLDivElement>(null)
  const [pdf, setPdf] = useState<PDFDocumentProxy>()
  const [sizes, setSizes] = useState<{ width: number; height: number }[]>([]) // at scale 1
  const [width, setWidth] = useState(0)
  const [near, setNear] = useState<ReadonlySet<number>>(new Set())
  const [error, setError] = useState<string>()

  useEffect(() => {
    const task = getDocument({ url })
    let stopped = false
    task.promise.then(
      async (document) => {
        const pages = await Promise.all(
          Array.from({ length: document.numPages }, (_, k) => document.getPage(k + 1)),
        )
        if (stopped) return
        setSizes(pages.map((page) => page.getViewport({ scale: 1 })))
        setPdf(document)
      },
      (reason: unknown) => {
        if (!stopped) setError(`Ce fichier ne peut pas être affiché : ${messageOf(reason)}`)
      },
    )
    return () => {
      stopped = true
      task.destroy()
    }
  }, [url])

  useEffect(() => {
    const element = box.current
    if (!element) return
    const observer = new ResizeObserver(() => setWidth(element.clientWidth))
    observer.observe(element)
    return () => observer.disconnect()
  }, [])

  const ready = pdf !== undefined && width > 0
  // The pages exist once the PDF is read and the width of the reader is known.
  useEffect(() => {
    const root = box.current
    if (!root || !ready) return
    const observer = new IntersectionObserver(
      (entries) =>
        setNear((previous) => {
          const next = new Set(previous)
          for (const entry of entries) {
            const page = Number((entry.target as HTMLElement).dataset.page)
            if (entry.isIntersecting) next.add(page)
            else next.delete(page)
          }
          return next
        }),
      { root, rootMargin: NEAR },
    )
    for (const page of root.querySelectorAll('[data-page]')) observer.observe(page)
    return () => observer.disconnect()
  }, [ready])

  const onScroll = usePageScroll(box, target, ready, onPage)
  const fit = sizes.length > 0 ? Math.min(width - 32, WIDEST) / sizes[0].width : 1
  const scale = (fit * zoom) / 100

  return (
    <div ref={box} className="reader-pages" onScroll={onScroll}>
      {error && <Notice>{error}</Notice>}
      {!pdf && !error && <p className="hint">Chargement du document…</p>}
      {pdf &&
        width > 0 &&
        sizes.map((size, k) => (
          <PdfPage
            key={k}
            pdf={pdf}
            number={k + 1}
            width={size.width * scale}
            height={size.height * scale}
            scale={scale}
            near={near.has(k + 1)}
          />
        ))}
    </div>
  )
}

type PageProps = {
  pdf: PDFDocumentProxy
  number: number
  width: number
  height: number
  scale: number
  near: boolean
}

function PdfPage({ pdf, number, width, height, scale, near }: PageProps) {
  const canvas = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    if (!near) return
    let stopped = false
    let task: RenderTask | undefined
    pdf.getPage(number).then((page) => {
      const target = canvas.current
      if (stopped || !target) return
      // Drawn at the density of the screen, shown at its size: sharp text.
      const viewport = page.getViewport({ scale: scale * (window.devicePixelRatio || 1) })
      target.width = Math.floor(viewport.width)
      target.height = Math.floor(viewport.height)
      task = page.render({ canvas: target, viewport })
      task.promise.catch(() => {}) // cancelled: the page left, or the zoom changed
    })
    return () => {
      stopped = true
      task?.cancel()
    }
  }, [pdf, number, scale, near])

  return (
    <div className="pdf-page" data-page={number} style={{ width, height }} aria-label={`Page ${number}`}>
      {near && <canvas ref={canvas} />}
    </div>
  )
}

