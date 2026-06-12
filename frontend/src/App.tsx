import { useState } from 'react'
import { fetchHealth, fetchRequests, fetchStats } from './lib/api'
import type { Range } from './lib/api'
import { formatCost, formatCount, formatTokens } from './lib/format'
import { usePolling } from './hooks/usePolling'
import { Panel } from './components/Panel'
import { StatCard } from './components/StatCard'
import { RangeTabs } from './components/RangeTabs'
import { StatusPill } from './components/StatusPill'
import { ModelTable } from './components/ModelTable'
import { RequestsTable } from './components/RequestsTable'
import { BudgetsPanel } from './components/BudgetsPanel'

export default function App() {
  const [range, setRange] = useState<Range>('7d')

  const health = usePolling(fetchHealth, 10_000)
  const stats = usePolling(() => fetchStats(range), 15_000, [range])
  const requests = usePolling(() => fetchRequests(range, 25), 15_000, [range])

  const s = stats.data

  return (
    <div className="mx-auto max-w-6xl px-4 py-8 sm:px-6">
      <header className="mb-8 flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <span className="text-2xl">⚡</span>
          <div>
            <h1 className="text-xl font-semibold text-ink">TokenPulse</h1>
            <p className="text-xs text-muted">AI spend, live from your proxy</p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <StatusPill health={health.data} error={health.error} />
          <RangeTabs value={range} onChange={setRange} />
        </div>
      </header>

      {stats.error && !s && (
        <Panel>
          <p className="text-sm text-danger">
            Can't reach the TokenPulse proxy: {stats.error}. Is it running on port 4100?
          </p>
        </Panel>
      )}

      {s && (
        <main className="space-y-6">
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
            <StatCard label="API cost" value={formatCost(s.api_cost_usd)} sub={rangeLabel(range)} />
            <StatCard label="Requests" value={formatCount(s.total_requests)} />
            <StatCard
              label="Tokens"
              value={`${formatTokens(s.total_input_tokens)} in / ${formatTokens(s.total_output_tokens)} out`}
            />
            <StatCard
              label="Subscription + local"
              value={formatTokens(s.subscription_tokens + s.local_tokens)}
              sub="tokens outside API billing"
            />
          </div>

          <Panel title="By model">
            <ModelTable models={s.models} />
          </Panel>

          {s.projects.length > 1 && (
            <Panel title="By project">
              <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
                {s.projects.map((p) => (
                  <div
                    key={p.tag}
                    className="flex items-center justify-between rounded-panel border border-panel-border bg-panel-strong px-4 py-3"
                  >
                    <span className="truncate font-mono text-xs text-ink">{p.tag || 'untagged'}</span>
                    <span className="ml-3 shrink-0 text-sm text-muted">
                      {formatCount(p.requests)} · <span className="text-ink">{formatCost(p.cost_usd)}</span>
                    </span>
                  </div>
                ))}
              </div>
            </Panel>
          )}

          <BudgetsPanel />

          <Panel title="Recent requests">
            <RequestsTable requests={requests.data?.requests ?? []} />
          </Panel>
        </main>
      )}

      <footer className="mt-10 text-center text-xs text-muted/60">
        {health.data && (
          <>
            DB {(health.data.db_size_bytes / 1024 / 1024).toFixed(1)} MB ·{' '}
            {formatCount(health.data.total_requests_tracked)} requests tracked all-time
          </>
        )}
      </footer>
    </div>
  )
}

function rangeLabel(r: Range): string {
  return { today: 'today', '7d': 'last 7 days', '30d': 'last 30 days', all: 'all time' }[r]
}
