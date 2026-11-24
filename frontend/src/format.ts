/* How numbers and dates are written in the interface, in French. */

/** A duration in minutes: "30 min", "1 h", "1 h 30". */
export function duration(minutes: number): string {
  const hours = Math.floor(minutes / 60)
  const rest = minutes % 60
  if (hours === 0) return `${minutes} min`
  return rest ? `${hours} h ${rest}` : `${hours} h`
}
