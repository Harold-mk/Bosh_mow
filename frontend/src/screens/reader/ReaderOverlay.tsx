import { useEffect, useRef } from 'react'
import { Reader } from './Reader.tsx'

type Props = {
  resourceId: number
  page: number
  backLabel: string // "Revenir à la question"
  onClose: () => void
}

/** The reader over a session, which goes on under it (R4): back in a click, or with
 *  Échap. The keys of the session wait meanwhile: the reader is a dialog. */
export function ReaderOverlay({ resourceId, page, backLabel, onClose }: Props) {
  const layer = useRef<HTMLDivElement>(null)

  useEffect(() => {
    layer.current?.focus()
  }, [])

  return (
    <div
      ref={layer}
      className="reader-overlay"
      role="dialog"
      aria-modal="true"
      aria-label="Lecteur"
      tabIndex={-1}
      onKeyDown={(event) => {
        if (event.key === 'Escape') onClose()
      }}
    >
      <Reader resourceId={resourceId} page={page} back={{ label: backLabel, onClick: onClose }} />
    </div>
  )
}
