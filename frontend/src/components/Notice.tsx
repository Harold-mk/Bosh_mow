import type { ReactNode } from 'react'
import { Icon } from './Icon.tsx'

/** A message about something that went wrong, with its reason. */
export function Notice({ children }: { children: ReactNode }) {
  return (
    <p className="notice" role="alert">
      <Icon name="alert" />
      <span>{children}</span>
    </p>
  )
}
