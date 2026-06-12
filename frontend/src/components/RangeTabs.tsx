import type { Range } from '../lib/api'

const RANGES: { value: Range; label: string }[] = [
  { value: 'today', label: 'Today' },
  { value: '7d', label: '7 days' },
  { value: '30d', label: '30 days' },
  { value: 'all', label: 'All time' },
]

export function RangeTabs({ value, onChange }: { value: Range; onChange: (r: Range) => void }) {
  return (
    <div className="flex gap-1 rounded-full border border-panel-border bg-panel-strong p-1">
      {RANGES.map((r) => (
        <button
          key={r.value}
          onClick={() => onChange(r.value)}
          className={
            'rounded-full px-3 py-1 text-sm transition-colors ' +
            (r.value === value
              ? 'bg-accent-soft font-medium text-accent-strong'
              : 'text-muted hover:text-ink')
          }
        >
          {r.label}
        </button>
      ))}
    </div>
  )
}
