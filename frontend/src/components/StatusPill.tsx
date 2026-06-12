import type { Health } from '../lib/api'
import { formatUptime } from '../lib/format'

export function StatusPill({ health, error }: { health: Health | null; error: string | null }) {
  const up = health !== null && error === null
  const paused = health?.proxy_paused ?? false
  const color = !up ? 'bg-danger' : paused ? 'bg-warn' : 'bg-accent'
  const label = !up ? 'Proxy unreachable' : paused ? 'Proxy paused' : `Proxy up ${formatUptime(health.uptime_seconds)}`

  return (
    <div className="flex items-center gap-2 rounded-full border border-panel-border bg-panel-strong px-3 py-1.5 text-sm text-muted">
      <span className={`h-2 w-2 rounded-full ${color} ${up && !paused ? 'animate-pulse' : ''}`} />
      <span>{label}</span>
      {health && <span className="text-xs opacity-60">v{health.version}</span>}
    </div>
  )
}
