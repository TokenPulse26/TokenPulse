import { useState } from 'react'
import {
  createBudget,
  deleteBudget,
  fetchBudgets,
  setBudgetEnabled,
} from '../lib/api'
import type { BudgetPeriod, BudgetStatus } from '../lib/api'
import { formatCost } from '../lib/format'
import { usePolling } from '../hooks/usePolling'
import { Panel } from './Panel'

export function BudgetsPanel() {
  // Bumped after every mutation so the poll restarts and refetches now.
  const [version, setVersion] = useState(0)
  const { data, error } = usePolling(fetchBudgets, 15_000, [version])
  const [actionError, setActionError] = useState<string | null>(null)

  const refresh = () => {
    setActionError(null)
    setVersion((v) => v + 1)
  }
  const run = async (action: () => Promise<unknown>) => {
    try {
      await action()
      refresh()
    } catch (e) {
      setActionError(e instanceof Error ? e.message : String(e))
    }
  }

  const budgets = data?.budgets ?? []

  return (
    <Panel title="Budgets">
      {(error || actionError) && (
        <p className="mb-3 text-sm text-danger">{actionError ?? error}</p>
      )}
      {budgets.length === 0 ? (
        <p className="mb-4 text-sm text-muted">
          No budgets yet — set a spending cap and TokenPulse will track it live.
        </p>
      ) : (
        <ul className="mb-4 space-y-3">
          {budgets.map((b) => (
            <BudgetRow
              key={b.id}
              budget={b}
              onToggle={() => void run(() => setBudgetEnabled(b.id, !b.enabled))}
              onDelete={() => {
                if (window.confirm(`Delete budget "${b.name}"?`)) {
                  void run(() => deleteBudget(b.id))
                }
              }}
            />
          ))}
        </ul>
      )}
      <CreateBudgetForm onCreate={(input) => void run(() => createBudget(input))} />
    </Panel>
  )
}

function BudgetRow({
  budget: b,
  onToggle,
  onDelete,
}: {
  budget: BudgetStatus
  onToggle: () => void
  onDelete: () => void
}) {
  const pct = Math.min(100, Math.max(0, b.percentage))
  const barColor = b.is_over ? 'bg-danger' : pct >= 80 ? 'bg-warn' : 'bg-accent'
  const scope =
    b.scope_kind === 'source_tag' ? `project ${b.scope_value ?? ''}` : b.provider_filter ?? 'all spend'

  return (
    <li className={`rounded-panel border border-panel-border bg-panel-strong p-4 ${b.enabled ? '' : 'opacity-50'}`}>
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0">
          <span className="font-medium text-ink">{b.name}</span>
          <span className="ml-2 text-xs text-muted">
            {b.period} · {scope}
          </span>
          {b.alert_active && (
            <span className="ml-2 rounded-full bg-danger/15 px-2 py-0.5 text-xs text-danger">alert</span>
          )}
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <button
            onClick={onToggle}
            className="rounded-full border border-panel-border px-2.5 py-1 text-xs text-muted transition-colors hover:text-ink"
          >
            {b.enabled ? 'Disable' : 'Enable'}
          </button>
          <button
            onClick={onDelete}
            className="rounded-full border border-panel-border px-2.5 py-1 text-xs text-muted transition-colors hover:border-danger/40 hover:text-danger"
          >
            Delete
          </button>
        </div>
      </div>
      <div className="mt-3 flex items-center gap-3">
        <div className="h-2 flex-1 overflow-hidden rounded-full bg-bg-soft">
          <div className={`h-full rounded-full ${barColor}`} style={{ width: `${pct}%` }} />
        </div>
        <span className="shrink-0 text-sm text-muted">
          <span className={b.is_over ? 'text-danger' : 'text-ink'}>{formatCost(b.current_spend)}</span>
          {' / '}
          {formatCost(b.threshold_usd)}
        </span>
      </div>
    </li>
  )
}

function CreateBudgetForm({ onCreate }: { onCreate: (input: { name: string; period: BudgetPeriod; threshold_usd: number; provider_filter?: string }) => void }) {
  const [name, setName] = useState('')
  const [period, setPeriod] = useState<BudgetPeriod>('monthly')
  const [threshold, setThreshold] = useState('')
  const [provider, setProvider] = useState('')

  const thresholdNum = Number(threshold)
  const valid = name.trim().length > 0 && Number.isFinite(thresholdNum) && thresholdNum > 0

  const inputClass =
    'rounded-lg border border-panel-border bg-bg-soft px-3 py-1.5 text-sm text-ink placeholder:text-muted/60 focus:border-accent/50 focus:outline-none'

  return (
    <form
      className="flex flex-wrap items-center gap-2"
      onSubmit={(e) => {
        e.preventDefault()
        if (!valid) return
        onCreate({
          name: name.trim(),
          period,
          threshold_usd: thresholdNum,
          ...(provider.trim() ? { provider_filter: provider.trim() } : {}),
        })
        setName('')
        setThreshold('')
        setProvider('')
      }}
    >
      <input className={`${inputClass} w-36`} placeholder="Budget name" value={name} onChange={(e) => setName(e.target.value)} />
      <select className={inputClass} value={period} onChange={(e) => setPeriod(e.target.value as BudgetPeriod)}>
        <option value="daily">Daily</option>
        <option value="weekly">Weekly</option>
        <option value="monthly">Monthly</option>
      </select>
      <input
        className={`${inputClass} w-24`}
        placeholder="$ limit"
        inputMode="decimal"
        value={threshold}
        onChange={(e) => setThreshold(e.target.value)}
      />
      <input
        className={`${inputClass} w-32`}
        placeholder="Provider (all)"
        value={provider}
        onChange={(e) => setProvider(e.target.value)}
      />
      <button
        type="submit"
        disabled={!valid}
        className="rounded-full bg-accent-soft px-4 py-1.5 text-sm font-medium text-accent-strong transition-opacity disabled:opacity-40"
      >
        Add budget
      </button>
    </form>
  )
}
