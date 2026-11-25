/* A study session runs in full screen (R16). In the app, the window itself goes full
   screen, through pywebview (WindowApi in backend/bosh_mow/app.py); in a browser, the
   page does. */

declare global {
  interface Window {
    pywebview?: { api: { fullscreen: (on: boolean) => Promise<void> } }
  }
}

const LEAVE_MS = 300 // a session screen that follows in full screen cancels the leaving
let leaving = 0

export function setFullscreen(on: boolean): void {
  window.clearTimeout(leaving)
  if (on) apply(true)
  else leaving = window.setTimeout(() => apply(false), LEAVE_MS)
}

function apply(on: boolean): void {
  // Only a comfort: if the window cannot change, the session goes on as it is.
  const app = window.pywebview?.api
  if (app) {
    app.fullscreen(on).catch(() => {})
  } else if (on && !document.fullscreenElement) {
    document.documentElement.requestFullscreen().catch(() => {})
  } else if (!on && document.fullscreenElement) {
    document.exitFullscreen().catch(() => {})
  }
}
