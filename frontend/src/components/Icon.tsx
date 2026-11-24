/* Icons in thin rounded strokes on a 24 px grid (docs/charte.md), from the mockups. */

const PATHS = {
  course: (
    <>
      <path d="M5 4h12a2 2 0 0 1 2 2v14H7a2 2 0 0 1-2-2z" />
      <path d="M5 18a2 2 0 0 1 2-2h12" />
    </>
  ),
  collapse: (
    <>
      <rect x="3.5" y="4.5" width="17" height="15" rx="3" />
      <path d="M9 4.5v15" />
      <path d="M15.5 10l-2 2 2 2" />
    </>
  ),
  expand: (
    <>
      <rect x="3.5" y="4.5" width="17" height="15" rx="3" />
      <path d="M9 4.5v15" />
      <path d="M13.5 10l2 2-2 2" />
    </>
  ),
  plus: <path d="M12 5v14M5 12h14" />,
  file: (
    <>
      <path d="M7 3h7l5 5v13H7z" />
      <path d="M14 3v5h5" />
    </>
  ),
  upload: (
    <>
      <path d="M12 16V4M7 9l5-5 5 5" />
      <path d="M5 15v4a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-4" />
    </>
  ),
  close: <path d="M6 6l12 12M18 6L6 18" />,
  check: <path d="M5 12.5l4.5 4.5L19 7.5" />,
  spark: (
    <path d="M12 3v4M12 17v4M3 12h4M17 12h4M6 6l2.5 2.5M15.5 15.5L18 18M6 18l2.5-2.5M15.5 8.5L18 6" />
  ),
  alert: (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 7.5v5.5M12 16.5v.01" />
    </>
  ),
}

export type IconName = keyof typeof PATHS

export function Icon({ name, size = 18 }: { name: IconName; size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {PATHS[name]}
    </svg>
  )
}
