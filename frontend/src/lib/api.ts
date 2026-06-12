// Typed client for the TokenPulse Rust proxy's local JSON API.
// In dev, Vite proxies /api and /health to the proxy (see vite.config.ts);
// in production builds the frontend is served by the proxy itself, so
// relative paths work in both cases.

export type Range = 'today' | '7d' | '30d' | 'all'

export interface Health {
  status: string
  service: string
  version: string
  port: number
  uptime_seconds: number
  proxy_paused: boolean
  total_requests_tracked: number
  dashboard_url: string
  db_path: string
  db_size_bytes: number
}

export interface ModelBreakdown {
  model: string
  provider: string
  requests: number
  tokens: number
  cost_usd: number
  type: 'api' | 'subscription' | 'local'
}

export interface ProjectBreakdown {
  tag: string
  requests: number
  cost_usd: number
}

export interface Stats {
  status: string
  range: Range
  total_requests: number
  total_input_tokens: number
  total_output_tokens: number
  api_cost_usd: number
  subscription_tokens: number
  local_tokens: number
  models: ModelBreakdown[]
  projects: ProjectBreakdown[]
}

export interface RequestRecord {
  id: number | null
  timestamp: string
  provider: string
  model: string
  input_tokens: number
  output_tokens: number
  cached_tokens: number
  cache_creation_tokens: number
  reasoning_tokens: number
  cost_usd: number
  cost_estimated: boolean
  latency_ms: number
  tokens_per_second: number
  time_to_first_token_ms: number
  is_streaming: boolean
  is_complete: boolean
  source_tag: string
  error_message: string | null
  provider_type: string
}

export interface RequestsResponse {
  status: string
  range: Range
  limit: number
  count: number
  requests: RequestRecord[]
}

export type BudgetPeriod = 'daily' | 'weekly' | 'monthly'

export interface BudgetStatus {
  id: number
  name: string
  period: BudgetPeriod
  threshold_usd: number
  provider_filter: string | null
  scope_kind: 'global' | 'source_tag'
  scope_value: string | null
  enabled: boolean
  current_spend: number
  percentage: number
  is_over: boolean
  warning_tier_pct: number | null
  warning_tier_label: string | null
  alert_active: boolean
  last_alert_triggered_at: string | null
}

export interface BudgetsResponse {
  status: string
  budgets: BudgetStatus[]
}

export interface BudgetInput {
  name: string
  period: BudgetPeriod
  threshold_usd: number
  provider_filter?: string
  scope_kind?: 'global' | 'source_tag'
  scope_value?: string
  enabled?: boolean
}

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(path, { headers: { Accept: 'application/json' } })
  if (!res.ok) throw new Error(`${path} returned HTTP ${res.status}`)
  const body = (await res.json()) as T & { status?: string; message?: string }
  if (body.status === 'error') throw new Error(body.message ?? `${path} returned an error`)
  return body
}

async function sendJson<T>(path: string, method: 'POST' | 'PUT' | 'DELETE', payload?: unknown): Promise<T> {
  const res = await fetch(path, {
    method,
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: payload === undefined ? undefined : JSON.stringify(payload),
  })
  const body = (await res.json()) as T & { status?: string; message?: string }
  if (!res.ok || body.status === 'error') {
    throw new Error(body.message ?? `${path} returned HTTP ${res.status}`)
  }
  return body
}

export const fetchHealth = () => getJson<Health>('/api/health')
export const fetchStats = (range: Range) => getJson<Stats>(`/api/stats?range=${range}`)
export const fetchRequests = (range: Range, limit = 25) =>
  getJson<RequestsResponse>(`/api/requests?range=${range}&limit=${limit}`)

export const fetchBudgets = () => getJson<BudgetsResponse>('/api/budgets')
export const createBudget = (input: BudgetInput) => sendJson<{ id: number }>('/api/budgets', 'POST', input)
export const updateBudget = (id: number, input: BudgetInput) =>
  sendJson<unknown>(`/api/budgets/${id}`, 'PUT', input)
export const setBudgetEnabled = (id: number, enabled: boolean) =>
  sendJson<unknown>(`/api/budgets/${id}/enabled`, 'PUT', { enabled })
export const deleteBudget = (id: number) => sendJson<unknown>(`/api/budgets/${id}`, 'DELETE')
