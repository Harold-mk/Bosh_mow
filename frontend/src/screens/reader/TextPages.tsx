import { useEffect, useRef, useState } from 'react'
import { getResourcePages, messageOf, type PageText } from '../../api.ts'
import { Notice } from '../../components/Notice.tsx'
import { type PagesProps, usePageScroll } from './pageScroll.ts'

/** A Markdown file on a single white sheet, section after section, as its text. */
export function TextPages({
  resourceId,
  zoom,
  target,
  onPage,
}: PagesProps & { resourceId: number }) {
  const box = useRef<HTMLDivElement>(null)
  const [pages, setPages] = useState<PageText[]>()
  const [error, setError] = useState<string>()

  useEffect(() => {
    getResourcePages(resourceId).then(setPages, (reason: unknown) => setError(messageOf(reason)))
  }, [resourceId])

  const onScroll = usePageScroll(box, target, pages !== undefined, onPage)
  return (
    <div ref={box} className="reader-pages" onScroll={onScroll}>
      {error && <Notice>{error}</Notice>}
      {pages && (
        <article className="text-sheet" style={{ fontSize: (15 * zoom) / 100 }}>
          {pages.map((page) => (
            <section key={page.number} data-page={page.number} className="text-section">
              {page.text.trim()}
            </section>
          ))}
        </article>
      )}
    </div>
  )
}
