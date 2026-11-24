/* The logo and the name of the app, drawn in dots like a light display (docs/charte.md). */

// A graduation cap over three rising bars: one string per row of the 11 × 11 grid.
const LOGO = [
  '....###....',
  '..#######..',
  '###########',
  '..#######.#',
  '....###...#',
  '..........#',
  '...........',
  '........###',
  '....###.###',
  '###.###.###',
  '###.###.###',
]

// BOSH MOW: letters of 5 × 7 cells, each cell drawn with 2 × 2 dots.
const NAME = [
  '####...###...####.#...#...#...#..###..#...#',
  '#...#.#...#.#.....#...#...##.##.#...#.#...#',
  '#...#.#...#.#.....#...#...#.#.#.#...#.#...#',
  '####..#...#..###..#####...#.#.#.#...#.#.#.#',
  '#...#.#...#.....#.#...#...#...#.#...#.#.#.#',
  '#...#.#...#.....#.#...#...#...#.#...#.##.##',
  '####...###..####..#...#...#...#..###..#...#',
]

/** The cells that are set in a grid, as [column, row]. */
function cells(grid: string[]): [number, number][] {
  return grid.flatMap((row, y) =>
    [...row].flatMap((cell, x): [number, number][] => (cell === '#' ? [[x, y]] : [])),
  )
}

const LOGO_DOTS = cells(LOGO).map(([x, y]) => [12 + 4 * x, 12 + 4 * y])
const NAME_DOTS = cells(NAME).flatMap(([x, y]) =>
  [0.25, 0.75].flatMap((dx) => [0.25, 0.75].map((dy) => [x + dx, y + dy])),
)

export function Logo({ size }: { size: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 64 64" aria-hidden="true">
      <rect width="64" height="64" rx="19" fill="currentColor" />
      <g fill="#ffffff">
        {LOGO_DOTS.map(([x, y]) => (
          <circle key={`${x},${y}`} cx={x} cy={y} r="1.75" />
        ))}
      </g>
    </svg>
  )
}

export function Wordmark({ height }: { height: number }) {
  const columns = NAME[0].length
  const rows = NAME.length
  return (
    <svg
      width={(height * columns) / rows}
      height={height}
      viewBox={`0 0 ${columns} ${rows}`}
      fill="currentColor"
      role="img"
      aria-label="Bosh mow"
    >
      {NAME_DOTS.map(([x, y]) => (
        <circle key={`${x},${y}`} cx={x} cy={y} r="0.215" />
      ))}
    </svg>
  )
}
