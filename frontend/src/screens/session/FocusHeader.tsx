import type { ReactNode } from 'react'
import { Logo, Wordmark } from '../../components/Brand.tsx'

/** The slim header of a session in full screen: the app, what is studied, and the
 *  way out. */
export function FocusHeader({ label, action }: { label: string; action?: ReactNode }) {
  return (
    <header className="focus-header">
      <Logo size={28} />
      <Wordmark height={13} />
      <span className="label">{label}</span>
      {action}
    </header>
  )
}
