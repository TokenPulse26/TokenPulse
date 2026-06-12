import type { RequestRecord } from '../lib/api'
import { formatCost, formatTokens, formatTimestamp } from '../lib/format'

export function RequestsTable({ requests }: { requests: RequestRecord[] }) {
  if (requests.length === 0) {
    return <p className="text-sm text-muted">No requests in this range.</p>
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-panel-border text-left text-xs uppercase tracking-wider text-muted">
            <th className="pb-2 pr-4 font-medium">Time</th>
            <th className="pb-2 pr-4 font-medium">Model</th>
            <th className="pb-2 pr-4 text-right font-medium">In</th>
            <th className="pb-2 pr-4 text-right font-medium">Out</th>
            <th className="pb-2 pr-4 text-right font-medium">Cached</th>
            <th className="pb-2 pr-4 text-right font-medium">Latency</th>
            <th className="pb-2 text-right font-medium">Cost</th>
          </tr>
        </thead>
        <tbody>
          {requests.map((r, i) => (
            <tr key={r.id ?? i} className="border-b border-panel-border/50 last:border-0">
              <td className="whitespace-nowrap py-2 pr-4 text-muted">{formatTimestamp(r.timestamp)}</td>
              <td className="py-2 pr-4">
                <span className="font-mono text-xs text-ink">{r.model || '—'}</span>
                {!r.is_complete && (
                  <span className="ml-2 rounded-full bg-danger/15 px-1.5 py-0.5 text-xs text-danger" title={r.error_message ?? 'incomplete'}>
                    err
                  </span>
                )}
                {r.is_streaming && <span className="ml-2 text-xs text-muted" title="streamed">≈</span>}
              </td>
              <td className="py-2 pr-4 text-right text-muted">{formatTokens(r.input_tokens)}</td>
              <td className="py-2 pr-4 text-right text-muted">{formatTokens(r.output_tokens)}</td>
              <td className="py-2 pr-4 text-right text-muted">{r.cached_tokens > 0 ? formatTokens(r.cached_tokens) : '—'}</td>
              <td className="py-2 pr-4 text-right text-muted">{r.latency_ms > 0 ? `${(r.latency_ms / 1000).toFixed(1)}s` : '—'}</td>
              <td className="py-2 text-right text-ink">{formatCost(r.cost_usd, r.cost_estimated)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
