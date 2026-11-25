import { type RefObject, useEffect, useRef } from 'react'

/** Where to scroll: `at` makes each request new, even to the same page. */
export type Target = { page: number; at: number }

/** What the pages of the reader take, whatever the kind of file. */
export type PagesProps = {
  zoom: number // in %
  target: Target
  onPage: (page: number) => void // the page in view, as the reading scrolls
}

/** Scroll to the target once the pages are laid out, and tell which page is in view
 *  (the last one whose top is above the upper part of the view). */
export function usePageScroll(
  box: RefObject<HTMLDivElement | null>,
  target: Target,
  ready: boolean,
  onPage: (page: number) => void,
) {
  const frame = useRef(0)

  useEffect(() => {
    const root = box.current
    if (!root || !ready) return
    const page = root.querySelector<HTMLElement>(`[data-page="${target.page}"]`)
    if (page) root.scrollTop = page.offsetTop - 16
  }, [box, target, ready])

  return () => {
    if (frame.current) return
    frame.current = requestAnimationFrame(() => {
      frame.current = 0
      const root = box.current
      if (!root) return
      const top = root.scrollTop + 80
      let found = 1
      for (const page of root.querySelectorAll<HTMLElement>('[data-page]')) {
        if (page.offsetTop > top) break
        found = Number(page.dataset.page)
      }
      onPage(found)
    })
  }
}
