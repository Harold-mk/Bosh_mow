import './Segmented.css'

type Props<T> = {
  label: string // what is chosen, for screen readers
  options: { value: T; label: string }[]
  value: T
  onChange: (value: T) => void
  small?: boolean
  mono?: boolean // labels in JetBrains Mono, for numbers
}

/** One option to choose among a few, shown side by side. */
export function Segmented<T extends string | number>({
  label,
  options,
  value,
  onChange,
  small = false,
  mono = false,
}: Props<T>) {
  const classes = ['segmented', small && 'small', mono && 'mono'].filter(Boolean)
  return (
    <div role="radiogroup" aria-label={label} className={classes.join(' ')}>
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          role="radio"
          aria-checked={option.value === value}
          onClick={() => onChange(option.value)}
        >
          {option.label}
        </button>
      ))}
    </div>
  )
}
