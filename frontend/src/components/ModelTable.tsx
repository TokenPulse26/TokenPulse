import type { ModelBreakdown } from '../lib/api'
import { formatCost, formatCount, formatTokens } from '../lib/format'

const TYPE_BADGE: Record<ModelBreakdown['type'], string> = {
  api: 'text-accent-strong bg-accent-soft',
  subscription: 'text-warn bg-warn/10',
  local: 'text-muted bg-bg-soft',
}

export function ModelTable({ models }: { models: ModelBreakdown[] }) {
  if (models.length === 0) {
    return <p className="text-sm text-muted">No model activity in this range.</p>
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-panel-border text-left text-xs uppercase tracking-wider text-muted">
            <th className="pb-2 pr-4 font-medium">Model</th>
            <th className="pb-2 pr-4 font-medium">Provider</th>
            <th className="pb-2 pr-4 text-right font-medium">Requests</th>
            <th className="pb-2 pr-4 text-right font-medium">Tokens</th>
            <th className="pb-2 text-right font-medium">Cost</th>
          </tr>
        </thead>
        <tbody>
          {models.map((m) => (
            <tr key={`${m.provider}/${m.model}`} className="border-b border-panel-border/50 last:border-0">
              <td className="py-2 pr-4 font-mono text-xs text-ink">{m.model}</td>
              <td className="py-2 pr-4">
                <span className={`rounded-full px-2 py-0.5 text-xs ${TYPE_BADGE[m.type]}`}>{m.provider}</span>
              </td>
              <td className="py-2 pr-4 text-right text-muted">{formatCount(m.requests)}</td>
              <td className="py-2 pr-4 text-right text-muted">{formatTokens(m.tokens)}</td>
              <td className="py-2 text-right text-ink">{formatCost(m.cost_usd)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
