use rusqlite::{params, Connection, Result};
use serde::{Deserialize, Serialize};

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct RequestRecord {
    pub id: Option<i64>,
    pub timestamp: String,
    pub provider: String,
    pub model: String,
    pub input_tokens: i64,
    pub output_tokens: i64,
    pub cached_tokens: i64,
    pub reasoning_tokens: i64,
    pub cost_usd: f64,
    pub latency_ms: i64,
    pub tokens_per_second: f64,
    pub time_to_first_token_ms: i64,
    pub is_streaming: bool,
    pub is_complete: bool,
    pub source_tag: String,
    pub error_message: Option<String>,
    pub provider_type: String,
}

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct CostSummary {
    pub total_api_cost: f64,
    pub total_subscription_tokens: i64,
    pub total_local_tokens: i64,
}

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct DailyStats {
    pub date: String,
    pub total_cost: f64,
    pub total_requests: i64,
    pub total_input_tokens: i64,
    pub total_output_tokens: i64,
}

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct DailyProviderStat {
    pub date: String,
    pub provider: String,
    pub cost: f64,
}

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct ModelStats {
    pub model: String,
    pub provider: String,
    pub total_cost: f64,
    pub total_requests: i64,
    pub total_tokens: i64,
}

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct ReliabilitySummary {
    pub total_requests: i64,
    pub successful_requests: i64,
    pub failed_requests: i64,
    pub success_rate_pct: f64,
    pub avg_latency_ms: f64,
    pub slow_requests: i64,
    pub slow_request_pct: f64,
}

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct ProviderReliabilityStat {
    pub provider: String,
    pub model: String,
    pub total_requests: i64,
    pub failed_requests: i64,
    pub success_rate_pct: f64,
    pub avg_latency_ms: f64,
    pub max_latency_ms: i64,
}

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct ReliabilityAnomaly {
    pub kind: String,
    pub provider: String,
    pub model: String,
    pub severity: String,
    pub summary: String,
    pub recent_requests: i64,
    pub baseline_requests: i64,
    pub recent_value: f64,
    pub baseline_value: f64,
    pub recent_cost: f64,
    pub delta_pct: f64,
    pub recommendation: String,
    pub fallback_model: Option<String>,
}

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct ReliabilitySnapshot {
    pub range: String,
    pub summary: ReliabilitySummary,
    pub providers: Vec<ProviderReliabilityStat>,
    pub anomalies: Vec<ReliabilityAnomaly>,
}

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct ContextAuditFinding {
    pub key: String,
    pub title: String,
    pub category: String,
    pub severity: String,
    pub confidence: String,
    pub summary: String,
    pub requests: i64,
    pub estimated_cost_impact_usd: f64,
    pub top_model: Option<String>,
    pub top_provider: Option<String>,
    pub filter_hint: Option<String>,
    pub impact_label: String,
    pub recommendation: String,
}

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct ContextAuditSnapshot {
    pub range: String,
    pub score: i64,
    pub estimated_savings_usd: f64,
    pub high_confidence_count: i64,
    pub waste_findings_count: i64,
    pub opportunity_findings_count: i64,
    pub findings: Vec<ContextAuditFinding>,
}

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct NotificationEvent {
    pub id: i64,
    pub kind: String,
    pub title: String,
    pub body: String,
    pub severity: String,
    pub created_at: String,
    pub dedupe_key: String,
}

fn fallback_model_for(model: &str) -> Option<&'static str> {
    match model.trim().to_lowercase().as_str() {
        "claude-opus-4-6" => Some("claude-sonnet-4-6"),
        "claude-sonnet-4-6" => Some("claude-haiku-3-5"),
        "gpt-4o" => Some("gpt-4o-mini"),
        "gpt-4.1" => Some("gpt-4.1-mini"),
        "gpt-4.1-mini" => Some("gpt-4.1-nano"),
        _ => None,
    }
}

fn reliability_recommendation(kind: &str, model: &str) -> (String, Option<String>) {
    if let Some(fallback) = fallback_model_for(model) {
        return match kind {
            "latency_spike" => (
                format!(
                    "Route time-sensitive work to {} until latency settles. Keep {} for higher-value prompts only.",
                    fallback, model
                ),
                Some(fallback.to_string()),
            ),
            _ => (
                format!(
                    "Retry traffic on {} or your next-cheapest stable model while {} is erroring. This reduces wasted retries and protects interactive flows.",
                    fallback, model
                ),
                Some(fallback.to_string()),
            ),
        };
    }

    match kind {
        "latency_spike" => (
            "Avoid long-running interactive prompts on this model for now. Keep a second provider ready as a manual fallback.".to_string(),
            None,
        ),
        _ => (
            "This model is failing more than normal. Add a provider-level fallback or temporarily pin critical work to a more stable model.".to_string(),
            None,
        ),
    }
}

#[derive(Debug)]
struct TopOccurrence {
    model: Option<String>,
    provider: Option<String>,
    model_count: i64,
    provider_count: i64,
}

fn context_audit_score_penalty(severity: &str, confidence: &str, impact_usd: f64, requests: i64) -> f64 {
    let severity_weight = match severity {
        "high" => 1.0,
        "medium" => 0.6,
        _ => 0.3,
    };
    let confidence_weight = match confidence {
        "high" => 1.0,
        "medium" => 0.7,
        _ => 0.45,
    };
    let cost_factor = (impact_usd * 4.0).min(20.0);
    let volume_factor = ((requests as f64) / 4.0).min(10.0);
    (severity_weight * confidence_weight * (cost_factor + volume_factor)).min(25.0)
}

fn fetch_top_occurrence(
    conn: &Connection,
    filter_clause: &str,
) -> Result<TopOccurrence> {
    let model_query = format!(
        "SELECT model, COUNT(*) as cnt
         FROM requests {}
         GROUP BY model
         ORDER BY cnt DESC, model ASC
         LIMIT 1",
        filter_clause
    );
    let provider_query = format!(
        "SELECT provider, COUNT(*) as cnt
         FROM requests {}
         GROUP BY provider
         ORDER BY cnt DESC, provider ASC
         LIMIT 1",
        filter_clause
    );

    let model_result = conn.query_row(&model_query, [], |row| {
        Ok((row.get::<_, String>(0)?, row.get::<_, i64>(1)?))
    });
    let provider_result = conn.query_row(&provider_query, [], |row| {
        Ok((row.get::<_, String>(0)?, row.get::<_, i64>(1)?))
    });

    let (model, model_count) = match model_result {
        Ok((model, count)) => (Some(model), count),
        Err(rusqlite::Error::QueryReturnedNoRows) => (None, 0),
        Err(e) => return Err(e),
    };
    let (provider, provider_count) = match provider_result {
        Ok((provider, count)) => (Some(provider), count),
        Err(rusqlite::Error::QueryReturnedNoRows) => (None, 0),
        Err(e) => return Err(e),
    };

    Ok(TopOccurrence {
        model,
        provider,
        model_count,
        provider_count,
    })
}

fn filter_hint_for(
    key: &str,
    requests: i64,
    top_model: Option<&str>,
    top_provider: Option<&str>,
) -> Option<String> {
    if requests <= 0 {
        return None;
    }

    let route_hint = match (top_model, top_provider) {
        (Some(model), Some(provider)) => format!(" Most affected: {} via {}.", model, provider),
        (Some(model), None) => format!(" Most affected model: {}.", model),
        (None, Some(provider)) => format!(" Most affected provider: {}.", provider),
        (None, None) => String::new(),
    };

    Some(match key {
        "failed_requests" => format!(
            "Filter recent requests to failed paid calls in this range.{}",
            route_hint
        ),
        "overprompting" => format!(
            "Filter recent requests to very large prompts with tiny outputs.{}",
            route_hint
        ),
        "cache_underuse" => format!(
            "Filter recent requests to 4K+ input calls with no cache signal.{}",
            route_hint
        ),
        "premium_small_tasks" => format!(
            "Filter recent requests to small jobs on premium models.{}",
            route_hint
        ),
        "local_model_opportunity" => format!(
            "Filter recent requests to sub-500-token API calls.{}",
            route_hint
        ),
        _ => format!("Filter recent requests to matching candidates.{}", route_hint),
    })
}

pub fn init_db(path: &str) -> Result<Connection> {
    let conn = Connection::open(path)?;

    // Enable WAL mode for better concurrent read/write performance
    conn.execute_batch("PRAGMA journal_mode=WAL;")?;

    conn.execute_batch(
        "
        CREATE TABLE IF NOT EXISTS requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            provider TEXT NOT NULL,
            model TEXT NOT NULL,
            input_tokens INTEGER NOT NULL DEFAULT 0,
            output_tokens INTEGER NOT NULL DEFAULT 0,
            cached_tokens INTEGER NOT NULL DEFAULT 0,
            reasoning_tokens INTEGER NOT NULL DEFAULT 0,
            cost_usd REAL NOT NULL DEFAULT 0.0,
            latency_ms INTEGER NOT NULL DEFAULT 0,
            tokens_per_second REAL NOT NULL DEFAULT 0.0,
            time_to_first_token_ms INTEGER NOT NULL DEFAULT 0,
            is_streaming INTEGER NOT NULL DEFAULT 0,
            is_complete INTEGER NOT NULL DEFAULT 1,
            source_tag TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            provider_type TEXT NOT NULL DEFAULT 'api'
        );

        CREATE TABLE IF NOT EXISTS pricing (
            model TEXT NOT NULL,
            provider TEXT NOT NULL,
            input_cost_per_million_tokens REAL NOT NULL DEFAULT 0.0,
            output_cost_per_million_tokens REAL NOT NULL DEFAULT 0.0,
            context_window_tokens INTEGER NOT NULL DEFAULT 0,
            is_custom INTEGER NOT NULL DEFAULT 0,
            last_updated TEXT NOT NULL DEFAULT (datetime('now')),
            PRIMARY KEY (model, provider)
        );

        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_requests_timestamp ON requests(timestamp);
        CREATE INDEX IF NOT EXISTS idx_requests_provider ON requests(provider);
        CREATE INDEX IF NOT EXISTS idx_requests_model ON requests(model);
        CREATE INDEX IF NOT EXISTS idx_requests_source_tag ON requests(source_tag);

        CREATE TABLE IF NOT EXISTS budgets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            period TEXT NOT NULL CHECK(period IN ('daily','weekly','monthly')),
            threshold_usd REAL NOT NULL,
            provider_filter TEXT,
            scope_kind TEXT NOT NULL DEFAULT 'global' CHECK(scope_kind IN ('global','source_tag')),
            scope_value TEXT,
            enabled INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS budget_alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            budget_id INTEGER NOT NULL,
            triggered_at TEXT NOT NULL DEFAULT (datetime('now')),
            resolved_at TEXT,
            current_spend REAL NOT NULL,
            threshold_usd REAL NOT NULL,
            FOREIGN KEY (budget_id) REFERENCES budgets(id)
        );

        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kind TEXT NOT NULL,
            title TEXT NOT NULL,
            body TEXT NOT NULL,
            severity TEXT NOT NULL DEFAULT 'info',
            dedupe_key TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            delivered_at TEXT,
            resolved_at TEXT
        );

        CREATE UNIQUE INDEX IF NOT EXISTS idx_notifications_active_dedupe
            ON notifications(dedupe_key)
            WHERE resolved_at IS NULL;

        CREATE INDEX IF NOT EXISTS idx_notifications_delivered
            ON notifications(delivered_at, created_at DESC);
    ",
    )?;

    // Migrations: add columns if they don't exist
    let _ = conn.execute("ALTER TABLE requests ADD COLUMN error_message TEXT", []);
    let _ = conn.execute(
        "ALTER TABLE requests ADD COLUMN provider_type TEXT NOT NULL DEFAULT 'api'",
        [],
    );
    let _ = conn.execute(
        "ALTER TABLE budgets ADD COLUMN scope_kind TEXT NOT NULL DEFAULT 'global'",
        [],
    );
    let _ = conn.execute("ALTER TABLE budgets ADD COLUMN scope_value TEXT", []);
    let _ = conn.execute("ALTER TABLE budget_alerts ADD COLUMN resolved_at TEXT", []);
    conn.execute_batch(
        "
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kind TEXT NOT NULL,
            title TEXT NOT NULL,
            body TEXT NOT NULL,
            severity TEXT NOT NULL DEFAULT 'info',
            dedupe_key TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            delivered_at TEXT,
            resolved_at TEXT
        );
        CREATE UNIQUE INDEX IF NOT EXISTS idx_notifications_active_dedupe
            ON notifications(dedupe_key)
            WHERE resolved_at IS NULL;
        CREATE INDEX IF NOT EXISTS idx_notifications_delivered
            ON notifications(delivered_at, created_at DESC);
    ",
    )?;

    migrate_pricing_table(&conn)?;

    Ok(conn)
}

fn migrate_pricing_table(conn: &Connection) -> Result<()> {
    let primary_key_columns: Vec<String> = {
        let mut stmt = conn.prepare("PRAGMA table_info(pricing)")?;
        let rows = stmt.query_map([], |row| {
            Ok((row.get::<_, String>(1)?, row.get::<_, i64>(5)?))
        })?;
        rows.filter_map(|row| row.ok())
            .filter(|(_, pk_order)| *pk_order > 0)
            .map(|(name, _)| name)
            .collect()
    };

    let already_migrated = primary_key_columns.len() == 2
        && primary_key_columns.iter().any(|c| c == "model")
        && primary_key_columns.iter().any(|c| c == "provider");

    if already_migrated {
        return Ok(());
    }

    conn.execute_batch(
        "BEGIN;
         CREATE TABLE IF NOT EXISTS pricing_new (
             model TEXT NOT NULL,
             provider TEXT NOT NULL,
             input_cost_per_million_tokens REAL NOT NULL DEFAULT 0.0,
             output_cost_per_million_tokens REAL NOT NULL DEFAULT 0.0,
             context_window_tokens INTEGER NOT NULL DEFAULT 0,
             is_custom INTEGER NOT NULL DEFAULT 0,
             last_updated TEXT NOT NULL DEFAULT (datetime('now')),
             PRIMARY KEY (model, provider)
         );
         INSERT OR IGNORE INTO pricing_new (
             model, provider, input_cost_per_million_tokens, output_cost_per_million_tokens,
             context_window_tokens, is_custom, last_updated
         )
         SELECT model, provider, input_cost_per_million_tokens, output_cost_per_million_tokens,
                context_window_tokens, is_custom, last_updated
         FROM pricing;
         DROP TABLE pricing;
         ALTER TABLE pricing_new RENAME TO pricing;
         COMMIT;",
    )?;

    Ok(())
}

pub fn insert_request(conn: &Connection, req: &RequestRecord) -> Result<i64> {
    conn.execute(
        "INSERT INTO requests (timestamp, provider, model, input_tokens, output_tokens, cached_tokens, reasoning_tokens, cost_usd, latency_ms, tokens_per_second, time_to_first_token_ms, is_streaming, is_complete, source_tag, error_message, provider_type)
         VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12, ?13, ?14, ?15, ?16)",
        params![
            req.timestamp,
            req.provider,
            req.model,
            req.input_tokens,
            req.output_tokens,
            req.cached_tokens,
            req.reasoning_tokens,
            req.cost_usd,
            req.latency_ms,
            req.tokens_per_second,
            req.time_to_first_token_ms,
            req.is_streaming as i64,
            req.is_complete as i64,
            req.source_tag,
            req.error_message,
            req.provider_type,
        ],
    )?;
    Ok(conn.last_insert_rowid())
}

fn map_request_row(row: &rusqlite::Row<'_>) -> rusqlite::Result<RequestRecord> {
    Ok(RequestRecord {
        id: Some(row.get(0)?),
        timestamp: row.get(1)?,
        provider: row.get(2)?,
        model: row.get(3)?,
        input_tokens: row.get(4)?,
        output_tokens: row.get(5)?,
        cached_tokens: row.get(6)?,
        reasoning_tokens: row.get(7)?,
        cost_usd: row.get(8)?,
        latency_ms: row.get(9)?,
        tokens_per_second: row.get(10)?,
        time_to_first_token_ms: row.get(11)?,
        is_streaming: row.get::<_, i64>(12)? != 0,
        is_complete: row.get::<_, i64>(13)? != 0,
        source_tag: row.get(14)?,
        error_message: row.get(15)?,
        provider_type: row
            .get::<_, Option<String>>(16)?
            .unwrap_or_else(|| "api".to_string()),
    })
}

pub fn get_recent_requests(conn: &Connection, limit: u32) -> Result<Vec<RequestRecord>> {
    let mut stmt = conn.prepare(
        "SELECT id, timestamp, provider, model, input_tokens, output_tokens, cached_tokens, reasoning_tokens, cost_usd, latency_ms, tokens_per_second, time_to_first_token_ms, is_streaming, is_complete, source_tag, error_message, COALESCE(provider_type, 'api')
         FROM requests ORDER BY timestamp DESC LIMIT ?1"
    )?;

    let records = stmt
        .query_map(params![limit], map_request_row)?
        .collect::<Result<Vec<_>>>()?;

    Ok(records)
}

pub fn get_daily_stats(conn: &Connection, days: u32) -> Result<Vec<DailyStats>> {
    let mut stmt = conn.prepare(
        "SELECT
            date(timestamp) as date,
            SUM(cost_usd) as total_cost,
            COUNT(*) as total_requests,
            SUM(input_tokens) as total_input_tokens,
            SUM(output_tokens) as total_output_tokens
         FROM requests
         WHERE timestamp >= datetime('now', ?1)
         GROUP BY date(timestamp)
         ORDER BY date ASC",
    )?;

    let days_param = format!("-{} days", days);
    let records = stmt
        .query_map(params![days_param], |row| {
            Ok(DailyStats {
                date: row.get(0)?,
                total_cost: row.get(1)?,
                total_requests: row.get(2)?,
                total_input_tokens: row.get(3)?,
                total_output_tokens: row.get(4)?,
            })
        })?
        .collect::<Result<Vec<_>>>()?;

    Ok(records)
}

pub fn upsert_pricing(
    conn: &Connection,
    model: &str,
    provider: &str,
    input_per_million: f64,
    output_per_million: f64,
    context_window: i64,
) -> Result<()> {
    conn.execute(
        "INSERT INTO pricing (model, provider, input_cost_per_million_tokens, output_cost_per_million_tokens, context_window_tokens, is_custom, last_updated)
         VALUES (?1, ?2, ?3, ?4, ?5, 0, datetime('now'))
         ON CONFLICT(model, provider) DO UPDATE SET
             input_cost_per_million_tokens=excluded.input_cost_per_million_tokens,
             output_cost_per_million_tokens=excluded.output_cost_per_million_tokens,
             context_window_tokens=excluded.context_window_tokens,
             last_updated=excluded.last_updated
         WHERE is_custom=0",
        params![model, provider, input_per_million, output_per_million, context_window],
    )?;
    Ok(())
}

pub fn set_setting(conn: &Connection, key: &str, value: &str) -> Result<()> {
    conn.execute(
        "INSERT INTO settings (key, value, updated_at) VALUES (?1, ?2, datetime('now'))
         ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
        params![key, value],
    )?;
    Ok(())
}

pub fn get_price_for_model(
    conn: &Connection,
    model: &str,
    provider: Option<&str>,
) -> Result<Option<(f64, f64)>> {
    let model_lower = model.to_lowercase();
    let provider_lower = provider.map(str::to_lowercase);
    let result = if let Some(provider_lower) = provider_lower.as_deref() {
        conn.query_row(
            "SELECT input_cost_per_million_tokens, output_cost_per_million_tokens
             FROM pricing
             WHERE lower(model) = ?1 AND lower(provider) = ?2",
            params![model_lower, provider_lower],
            |row| Ok((row.get::<_, f64>(0)?, row.get::<_, f64>(1)?)),
        )
    } else {
        conn.query_row(
            "SELECT input_cost_per_million_tokens, output_cost_per_million_tokens
             FROM pricing
             WHERE lower(model) = ?1
             ORDER BY CASE WHEN is_custom = 1 THEN 0 ELSE 1 END, provider ASC
             LIMIT 1",
            params![model_lower],
            |row| Ok((row.get::<_, f64>(0)?, row.get::<_, f64>(1)?)),
        )
    };
    match result {
        Ok(v) => Ok(Some(v)),
        Err(rusqlite::Error::QueryReturnedNoRows) => Ok(None),
        Err(e) => Err(e),
    }
}

pub fn get_setting(conn: &Connection, key: &str) -> Result<Option<String>> {
    let result = conn.query_row(
        "SELECT value FROM settings WHERE key = ?1",
        params![key],
        |row| row.get::<_, String>(0),
    );
    match result {
        Ok(v) => Ok(Some(v)),
        Err(rusqlite::Error::QueryReturnedNoRows) => Ok(None),
        Err(e) => Err(e),
    }
}

pub fn get_all_requests(conn: &Connection) -> Result<Vec<RequestRecord>> {
    let mut stmt = conn.prepare(
        "SELECT id, timestamp, provider, model, input_tokens, output_tokens, cached_tokens, reasoning_tokens, cost_usd, latency_ms, tokens_per_second, time_to_first_token_ms, is_streaming, is_complete, source_tag, error_message, COALESCE(provider_type, 'api')
         FROM requests ORDER BY timestamp DESC"
    )?;
    let records = stmt
        .query_map([], map_request_row)?
        .collect::<Result<Vec<_>>>()?;
    Ok(records)
}

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct DashboardSummary {
    pub total_cost: f64,
    pub total_requests: i64,
    pub total_input_tokens: i64,
    pub total_output_tokens: i64,
}

fn time_range_filter(time_range: &str) -> String {
    match time_range {
        "today" => "WHERE timestamp >= datetime('now', 'start of day')".to_string(),
        "7d" => "WHERE timestamp >= datetime('now', '-7 days')".to_string(),
        "30d" => "WHERE timestamp >= datetime('now', '-30 days')".to_string(),
        _ => String::new(), // "all"
    }
}

pub fn get_summary_stats(conn: &Connection, time_range: &str) -> Result<DashboardSummary> {
    let where_clause = time_range_filter(time_range);
    let query = format!(
        "SELECT COALESCE(SUM(cost_usd), 0.0), COUNT(*), COALESCE(SUM(input_tokens), 0), COALESCE(SUM(output_tokens), 0)
         FROM requests {}",
        where_clause
    );
    conn.query_row(&query, [], |row| {
        Ok(DashboardSummary {
            total_cost: row.get(0)?,
            total_requests: row.get(1)?,
            total_input_tokens: row.get(2)?,
            total_output_tokens: row.get(3)?,
        })
    })
}

pub fn get_daily_stats_for_range(conn: &Connection, time_range: &str) -> Result<Vec<DailyStats>> {
    let where_clause = time_range_filter(time_range);
    let query = format!(
        "SELECT date(timestamp) as date, SUM(cost_usd), COUNT(*), SUM(input_tokens), SUM(output_tokens)
         FROM requests {} GROUP BY date(timestamp) ORDER BY date ASC",
        where_clause
    );
    let mut stmt = conn.prepare(&query)?;
    let records = stmt
        .query_map([], |row| {
            Ok(DailyStats {
                date: row.get(0)?,
                total_cost: row.get(1)?,
                total_requests: row.get(2)?,
                total_input_tokens: row.get(3)?,
                total_output_tokens: row.get(4)?,
            })
        })?
        .collect::<Result<Vec<_>>>()?;
    Ok(records)
}

pub fn get_daily_provider_stats_for_range(
    conn: &Connection,
    time_range: &str,
) -> Result<Vec<DailyProviderStat>> {
    let where_clause = time_range_filter(time_range);
    let query = format!(
        "SELECT date(timestamp) as date, provider, SUM(cost_usd) as cost
         FROM requests {} GROUP BY date(timestamp), provider ORDER BY date ASC",
        where_clause
    );
    let mut stmt = conn.prepare(&query)?;
    let records = stmt
        .query_map([], |row| {
            Ok(DailyProviderStat {
                date: row.get(0)?,
                provider: row.get(1)?,
                cost: row.get(2)?,
            })
        })?
        .collect::<Result<Vec<_>>>()?;
    Ok(records)
}

pub fn get_model_breakdown_for_range(
    conn: &Connection,
    time_range: &str,
) -> Result<Vec<ModelStats>> {
    let where_clause = time_range_filter(time_range);
    let query = format!(
        "SELECT model, provider, SUM(cost_usd), COUNT(*), SUM(input_tokens + output_tokens)
         FROM requests {} GROUP BY model, provider ORDER BY SUM(cost_usd) DESC",
        where_clause
    );
    let mut stmt = conn.prepare(&query)?;
    let records = stmt
        .query_map([], |row| {
            Ok(ModelStats {
                model: row.get(0)?,
                provider: row.get(1)?,
                total_cost: row.get(2)?,
                total_requests: row.get(3)?,
                total_tokens: row.get(4)?,
            })
        })?
        .collect::<Result<Vec<_>>>()?;
    Ok(records)
}

pub fn get_requests_for_range(
    conn: &Connection,
    limit: u32,
    time_range: &str,
) -> Result<Vec<RequestRecord>> {
    let where_clause = time_range_filter(time_range);
    let query = format!(
        "SELECT id, timestamp, provider, model, input_tokens, output_tokens, cached_tokens, reasoning_tokens, cost_usd, latency_ms, tokens_per_second, time_to_first_token_ms, is_streaming, is_complete, source_tag, error_message, COALESCE(provider_type, 'api')
         FROM requests {} ORDER BY timestamp DESC LIMIT {}",
        where_clause, limit
    );
    let mut stmt = conn.prepare(&query)?;
    let records = stmt
        .query_map([], map_request_row)?
        .collect::<Result<Vec<_>>>()?;
    Ok(records)
}

pub fn get_cost_summary(conn: &Connection, time_range: &str) -> Result<CostSummary> {
    let time_cond = match time_range {
        "today" => "timestamp >= datetime('now', 'start of day')",
        "7d" => "timestamp >= datetime('now', '-7 days')",
        "30d" => "timestamp >= datetime('now', '-30 days')",
        _ => "1=1",
    };

    let api_cost: f64 = conn.query_row(
        &format!("SELECT COALESCE(SUM(cost_usd), 0.0) FROM requests WHERE {} AND COALESCE(provider_type, 'api') = 'api'", time_cond),
        [],
        |row| row.get(0),
    )?;

    let sub_tokens: i64 = conn.query_row(
        &format!("SELECT COALESCE(SUM(input_tokens + output_tokens), 0) FROM requests WHERE {} AND provider_type = 'subscription'", time_cond),
        [],
        |row| row.get(0),
    )?;

    let local_tokens: i64 = conn.query_row(
        &format!("SELECT COALESCE(SUM(input_tokens + output_tokens), 0) FROM requests WHERE {} AND provider_type = 'local'", time_cond),
        [],
        |row| row.get(0),
    )?;

    Ok(CostSummary {
        total_api_cost: api_cost,
        total_subscription_tokens: sub_tokens,
        total_local_tokens: local_tokens,
    })
}

// ─── Budget types ────────────────────────────────────────────────────────────

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct Budget {
    pub id: i64,
    pub name: String,
    pub period: String,
    pub threshold_usd: f64,
    pub provider_filter: Option<String>,
    pub scope_kind: String,
    pub scope_value: Option<String>,
    pub enabled: bool,
    pub created_at: String,
}

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct BudgetStatus {
    pub id: i64,
    pub name: String,
    pub period: String,
    pub threshold_usd: f64,
    pub provider_filter: Option<String>,
    pub scope_kind: String,
    pub scope_value: Option<String>,
    pub enabled: bool,
    pub current_spend: f64,
    pub percentage: f64,
    pub is_over: bool,
    pub warning_tier_pct: Option<i64>,
    pub warning_tier_label: Option<String>,
    pub alert_active: bool,
    pub last_alert_triggered_at: Option<String>,
}

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct BudgetAlertHistoryItem {
    pub id: i64,
    pub budget_id: i64,
    pub budget_name: String,
    pub period: String,
    pub provider_filter: Option<String>,
    pub scope_kind: String,
    pub scope_value: Option<String>,
    pub triggered_at: String,
    pub resolved_at: Option<String>,
    pub current_spend: f64,
    pub threshold_usd: f64,
}

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct BudgetForecast {
    pub budget_id: i64,
    pub budget_name: String,
    pub period: String,
    pub provider_filter: Option<String>,
    pub scope_kind: String,
    pub scope_value: Option<String>,
    pub current_spend: f64,
    pub threshold_usd: f64,
    pub trailing_days: i64,
    pub average_daily_spend: f64,
    pub projected_period_spend: f64,
    pub remaining_budget: f64,
    pub days_until_threshold: Option<f64>,
    pub is_over: bool,
}

// ─── Budget functions ─────────────────────────────────────────────────────────

fn normalize_budget_scope(
    scope_kind: Option<&str>,
    scope_value: Option<&str>,
) -> Result<(String, Option<String>)> {
    let kind = match scope_kind
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .unwrap_or("global")
    {
        "global" => "global",
        "source_tag" | "project" => "source_tag",
        other => {
            return Err(rusqlite::Error::InvalidParameterName(format!(
                "invalid budget scope kind: {}",
                other
            )))
        }
    };

    let value = scope_value
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .map(str::to_string);

    if kind == "global" {
        Ok((kind.to_string(), None))
    } else if let Some(value) = value {
        Ok((kind.to_string(), Some(value)))
    } else {
        Err(rusqlite::Error::InvalidParameterName(
            "budget scope value is required".to_string(),
        ))
    }
}

fn budget_time_expr(period: &str) -> &str {
    match period {
        "daily" => "datetime('now', 'start of day')",
        "weekly" => "datetime('now', '-7 days')",
        _ => "datetime('now', '-30 days')",
    }
}

fn budget_warning_tier(percentage: f64) -> Option<(i64, &'static str)> {
    if percentage >= 100.0 {
        Some((100, "over_budget"))
    } else if percentage >= 95.0 {
        Some((95, "critical"))
    } else if percentage >= 80.0 {
        Some((80, "warning"))
    } else {
        None
    }
}

fn budget_spend_with_filters(
    conn: &Connection,
    time_expr: &str,
    provider_filter: Option<&str>,
    scope_kind: &str,
    scope_value: Option<&str>,
) -> Result<f64> {
    match (provider_filter, scope_kind, scope_value) {
        (Some(provider), "source_tag", Some(scope_value)) => conn.query_row(
            &format!(
                "SELECT COALESCE(SUM(cost_usd), 0.0) FROM requests \
                 WHERE timestamp >= {} AND COALESCE(provider_type,'api') = 'api' \
                 AND provider = ?1 AND COALESCE(source_tag, '') = ?2",
                time_expr
            ),
            params![provider, scope_value],
            |row| row.get(0),
        ),
        (Some(provider), _, _) => conn.query_row(
            &format!(
                "SELECT COALESCE(SUM(cost_usd), 0.0) FROM requests \
                 WHERE timestamp >= {} AND COALESCE(provider_type,'api') = 'api' \
                 AND provider = ?1",
                time_expr
            ),
            params![provider],
            |row| row.get(0),
        ),
        (None, "source_tag", Some(scope_value)) => conn.query_row(
            &format!(
                "SELECT COALESCE(SUM(cost_usd), 0.0) FROM requests \
                 WHERE timestamp >= {} AND COALESCE(provider_type,'api') = 'api' \
                 AND COALESCE(source_tag, '') = ?1",
                time_expr
            ),
            params![scope_value],
            |row| row.get(0),
        ),
        (None, _, _) => conn.query_row(
            &format!(
                "SELECT COALESCE(SUM(cost_usd), 0.0) FROM requests \
                 WHERE timestamp >= {} AND COALESCE(provider_type,'api') = 'api'",
                time_expr
            ),
            [],
            |row| row.get(0),
        ),
    }
}

fn budget_current_spend(conn: &Connection, budget: &Budget) -> Result<f64> {
    let time_expr = budget_time_expr(&budget.period);
    budget_spend_with_filters(
        conn,
        time_expr,
        budget.provider_filter.as_deref(),
        budget.scope_kind.as_str(),
        budget.scope_value.as_deref(),
    )
}

pub fn create_budget(
    conn: &Connection,
    name: &str,
    period: &str,
    threshold: f64,
    provider_filter: Option<&str>,
    scope_kind: Option<&str>,
    scope_value: Option<&str>,
) -> Result<i64> {
    let (scope_kind, scope_value) = normalize_budget_scope(scope_kind, scope_value)?;
    conn.execute(
        "INSERT INTO budgets (name, period, threshold_usd, provider_filter, scope_kind, scope_value, enabled, created_at)
         VALUES (?1, ?2, ?3, ?4, ?5, ?6, 1, datetime('now'))",
        params![name, period, threshold, provider_filter, scope_kind, scope_value],
    )?;
    Ok(conn.last_insert_rowid())
}

pub fn get_budgets(conn: &Connection) -> Result<Vec<Budget>> {
    let mut stmt = conn.prepare(
        "SELECT id, name, period, threshold_usd, provider_filter, COALESCE(scope_kind, 'global'), scope_value, enabled, created_at
         FROM budgets ORDER BY created_at ASC",
    )?;
    let records = stmt
        .query_map([], |row| {
            Ok(Budget {
                id: row.get(0)?,
                name: row.get(1)?,
                period: row.get(2)?,
                threshold_usd: row.get(3)?,
                provider_filter: row.get(4)?,
                scope_kind: row.get(5)?,
                scope_value: row.get(6)?,
                enabled: row.get::<_, i64>(7)? != 0,
                created_at: row.get(8)?,
            })
        })?
        .collect::<Result<Vec<_>>>()?;
    Ok(records)
}

pub fn update_budget(
    conn: &Connection,
    id: i64,
    name: &str,
    period: &str,
    threshold: f64,
    provider_filter: Option<&str>,
    scope_kind: Option<&str>,
    scope_value: Option<&str>,
    enabled: bool,
) -> Result<()> {
    let (scope_kind, scope_value) = normalize_budget_scope(scope_kind, scope_value)?;
    conn.execute(
        "UPDATE budgets
         SET name = ?1, period = ?2, threshold_usd = ?3, provider_filter = ?4,
             scope_kind = ?5, scope_value = ?6, enabled = ?7
         WHERE id = ?8",
        params![
            name,
            period,
            threshold,
            provider_filter,
            scope_kind,
            scope_value,
            enabled as i64,
            id
        ],
    )?;
    resolve_budget_alerts(conn, id)?;
    Ok(())
}

pub fn set_budget_enabled(conn: &Connection, id: i64, enabled: bool) -> Result<()> {
    conn.execute(
        "UPDATE budgets SET enabled = ?1 WHERE id = ?2",
        params![enabled as i64, id],
    )?;
    if !enabled {
        resolve_budget_alerts(conn, id)?;
    }
    Ok(())
}

pub fn delete_budget(conn: &Connection, id: i64) -> Result<()> {
    conn.execute(
        "DELETE FROM budget_alerts WHERE budget_id = ?1",
        params![id],
    )?;
    conn.execute("DELETE FROM budgets WHERE id = ?1", params![id])?;
    Ok(())
}

fn get_active_alert_metadata(conn: &Connection, budget_id: i64) -> Result<(bool, Option<String>)> {
    let mut stmt = conn.prepare(
        "SELECT triggered_at
         FROM budget_alerts
         WHERE budget_id = ?1 AND resolved_at IS NULL
         ORDER BY triggered_at DESC
         LIMIT 1",
    )?;
    let mut rows = stmt.query(params![budget_id])?;
    if let Some(row) = rows.next()? {
        Ok((true, Some(row.get(0)?)))
    } else {
        Ok((false, None))
    }
}

fn build_budget_status(conn: &Connection, budget: &Budget) -> Result<BudgetStatus> {
    let current_spend = budget_current_spend(conn, budget)?;
    let percentage = if budget.threshold_usd > 0.0 {
        (current_spend / budget.threshold_usd) * 100.0
    } else {
        0.0
    };
    let (alert_active, last_alert_triggered_at) = get_active_alert_metadata(conn, budget.id)?;

    let warning_tier = budget_warning_tier(percentage);

    Ok(BudgetStatus {
        id: budget.id,
        name: budget.name.clone(),
        period: budget.period.clone(),
        threshold_usd: budget.threshold_usd,
        provider_filter: budget.provider_filter.clone(),
        scope_kind: budget.scope_kind.clone(),
        scope_value: budget.scope_value.clone(),
        enabled: budget.enabled,
        current_spend,
        percentage,
        is_over: current_spend >= budget.threshold_usd,
        warning_tier_pct: warning_tier.map(|(pct, _)| pct),
        warning_tier_label: warning_tier.map(|(_, label)| label.to_string()),
        alert_active,
        last_alert_triggered_at,
    })
}

pub fn check_budgets(conn: &Connection) -> Result<Vec<BudgetStatus>> {
    let budgets = get_budgets(conn)?;
    budgets
        .iter()
        .filter(|b| b.enabled)
        .map(|budget| build_budget_status(conn, budget))
        .collect()
}

pub fn resolve_budget_alerts(conn: &Connection, budget_id: i64) -> Result<usize> {
    conn.execute(
        "UPDATE budget_alerts
         SET resolved_at = datetime('now')
         WHERE budget_id = ?1 AND resolved_at IS NULL",
        params![budget_id],
    )
}

pub fn record_alert(
    conn: &Connection,
    budget_id: i64,
    current_spend: f64,
    threshold: f64,
) -> Result<()> {
    conn.execute(
        "INSERT INTO budget_alerts (budget_id, triggered_at, current_spend, threshold_usd, resolved_at)
         VALUES (?1, datetime('now'), ?2, ?3, NULL)",
        params![budget_id, current_spend, threshold],
    )?;
    Ok(())
}

pub fn sync_budget_alerts(conn: &Connection) -> Result<Vec<BudgetStatus>> {
    let budgets = get_budgets(conn)?;
    let mut newly_triggered = Vec::new();

    for budget in budgets {
        let status = build_budget_status(conn, &budget)?;
        if !budget.enabled || !status.is_over {
            resolve_budget_alerts(conn, budget.id)?;
            continue;
        }

        if !status.alert_active {
            record_alert(conn, budget.id, status.current_spend, status.threshold_usd)?;
            let mut triggered = status.clone();
            triggered.alert_active = true;
            triggered.last_alert_triggered_at = Some(
                chrono::Utc::now()
                    .naive_utc()
                    .format("%Y-%m-%d %H:%M:%S")
                    .to_string(),
            );
            newly_triggered.push(triggered);
        }
    }

    Ok(newly_triggered)
}

pub fn get_budget_alert_history(
    conn: &Connection,
    limit: i64,
) -> Result<Vec<BudgetAlertHistoryItem>> {
    let bounded_limit = limit.clamp(1, 200);
    let mut stmt = conn.prepare(
        "SELECT a.id, a.budget_id, b.name, b.period, b.provider_filter,
                COALESCE(b.scope_kind, 'global'), b.scope_value,
                a.triggered_at, a.resolved_at, a.current_spend, a.threshold_usd
         FROM budget_alerts a
         INNER JOIN budgets b ON b.id = a.budget_id
         ORDER BY a.triggered_at DESC
         LIMIT ?1",
    )?;

    let rows = stmt.query_map(params![bounded_limit], |row| {
        Ok(BudgetAlertHistoryItem {
            id: row.get(0)?,
            budget_id: row.get(1)?,
            budget_name: row.get(2)?,
            period: row.get(3)?,
            provider_filter: row.get(4)?,
            scope_kind: row.get(5)?,
            scope_value: row.get(6)?,
            triggered_at: row.get(7)?,
            resolved_at: row.get(8)?,
            current_spend: row.get(9)?,
            threshold_usd: row.get(10)?,
        })
    })?;
    rows.collect()
}

fn forecast_trailing_days(period: &str) -> i64 {
    match period {
        "daily" => 1,
        "weekly" => 7,
        _ => 7,
    }
}

fn budget_trailing_average_daily_spend(
    conn: &Connection,
    budget: &Budget,
    trailing_days: i64,
) -> Result<f64> {
    let time_expr = format!("datetime('now', '-{} days')", trailing_days.max(1));

    let total_spend = budget_spend_with_filters(
        conn,
        &time_expr,
        budget.provider_filter.as_deref(),
        budget.scope_kind.as_str(),
        budget.scope_value.as_deref(),
    )?;

    Ok(total_spend / trailing_days.max(1) as f64)
}

fn create_notification(
    conn: &Connection,
    kind: &str,
    title: &str,
    body: &str,
    severity: &str,
    dedupe_key: &str,
) -> Result<Option<NotificationEvent>> {
    let updated = conn.execute(
        "INSERT OR IGNORE INTO notifications (kind, title, body, severity, dedupe_key) VALUES (?1, ?2, ?3, ?4, ?5)",
        params![kind, title, body, severity, dedupe_key],
    )?;

    if updated == 0 {
        return Ok(None);
    }

    let id = conn.last_insert_rowid();
    let event = conn.query_row(
        "SELECT id, kind, title, body, severity, created_at, dedupe_key FROM notifications WHERE id = ?1",
        params![id],
        |row| {
            Ok(NotificationEvent {
                id: row.get(0)?,
                kind: row.get(1)?,
                title: row.get(2)?,
                body: row.get(3)?,
                severity: row.get(4)?,
                created_at: row.get(5)?,
                dedupe_key: row.get(6)?,
            })
        },
    )?;
    Ok(Some(event))
}

fn resolve_notifications_matching(
    conn: &Connection,
    pattern: &str,
    active_keys: &[String],
) -> Result<usize> {
    let mut resolved = 0;
    let mut stmt = conn.prepare(
        "SELECT id, dedupe_key FROM notifications WHERE dedupe_key LIKE ?1 AND resolved_at IS NULL",
    )?;
    let rows = stmt.query_map(params![pattern], |row| {
        Ok((row.get::<_, i64>(0)?, row.get::<_, String>(1)?))
    })?;
    for row in rows {
        let (id, key) = row?;
        if !active_keys.iter().any(|active| active == &key) {
            resolved += conn.execute(
                "UPDATE notifications SET resolved_at = datetime('now') WHERE id = ?1 AND resolved_at IS NULL",
                params![id],
            )?;
        }
    }
    Ok(resolved)
}

pub fn get_undelivered_notifications(
    conn: &Connection,
    limit: i64,
) -> Result<Vec<NotificationEvent>> {
    let bounded_limit = limit.clamp(1, 100);
    let mut stmt = conn.prepare(
        "SELECT id, kind, title, body, severity, created_at, dedupe_key
         FROM notifications
         WHERE delivered_at IS NULL AND resolved_at IS NULL
         ORDER BY created_at ASC, id ASC
         LIMIT ?1",
    )?;
    let rows = stmt.query_map(params![bounded_limit], |row| {
        Ok(NotificationEvent {
            id: row.get(0)?,
            kind: row.get(1)?,
            title: row.get(2)?,
            body: row.get(3)?,
            severity: row.get(4)?,
            created_at: row.get(5)?,
            dedupe_key: row.get(6)?,
        })
    })?;
    rows.collect()
}

pub fn mark_notifications_delivered(conn: &Connection, ids: &[i64]) -> Result<usize> {
    let mut updated = 0;
    for id in ids {
        updated += conn.execute(
            "UPDATE notifications SET delivered_at = COALESCE(delivered_at, datetime('now')) WHERE id = ?1",
            params![id],
        )?;
    }
    Ok(updated)
}

pub fn sync_budget_notifications(conn: &Connection) -> Result<Vec<NotificationEvent>> {
    let budgets = get_budgets(conn)?;
    let mut events = Vec::new();
    let mut active_keys = Vec::new();

    for budget in budgets.into_iter().filter(|budget| budget.enabled) {
        let status = build_budget_status(conn, &budget)?;
        if let Some((tier_pct, tier_label)) = budget_warning_tier(status.percentage) {
            let dedupe_key = format!("budget:{}:tier:{}", budget.id, tier_pct);
            active_keys.push(dedupe_key.clone());
            let severity = if tier_pct >= 100 {
                "critical"
            } else if tier_pct >= 95 {
                "high"
            } else {
                "medium"
            };
            let title = if tier_pct >= 100 {
                format!("Budget exceeded: {}", budget.name)
            } else {
                format!("Budget {}% used: {}", tier_pct, budget.name)
            };
            let body = format!(
                "{} is at ${:.2} of ${:.2} ({:.0}%) for this {} budget.",
                budget.name,
                status.current_spend,
                status.threshold_usd,
                status.percentage,
                budget.period
            );
            if let Some(event) = create_notification(
                conn,
                &format!("budget_{}", tier_label),
                &title,
                &body,
                severity,
                &dedupe_key,
            )? {
                events.push(event);
            }
        }
    }

    resolve_notifications_matching(conn, "budget:%", &active_keys)?;
    Ok(events)
}

pub fn sync_reliability_notifications(
    conn: &Connection,
    range: &str,
) -> Result<Vec<NotificationEvent>> {
    let snapshot = get_reliability_snapshot(conn, range)?;
    let mut events = Vec::new();
    let mut active_keys = Vec::new();

    for anomaly in snapshot.anomalies.iter() {
        let dedupe_key = format!(
            "reliability:{}:{}:{}",
            anomaly.kind, anomaly.provider, anomaly.model
        );
        active_keys.push(dedupe_key.clone());
        let title = match anomaly.kind.as_str() {
            "error_spike" => format!("Reliability issue: {}", anomaly.model),
            _ => format!("Latency spike: {}", anomaly.model),
        };
        let body = anomaly.summary.clone();
        if let Some(event) = create_notification(
            conn,
            &format!("reliability_{}", anomaly.kind),
            &title,
            &body,
            &anomaly.severity,
            &dedupe_key,
        )? {
            events.push(event);
        }
    }

    resolve_notifications_matching(conn, "reliability:%", &active_keys)?;
    Ok(events)
}

pub fn get_budget_forecasts(conn: &Connection) -> Result<Vec<BudgetForecast>> {
    let budgets = get_budgets(conn)?;
    let mut forecasts = Vec::new();

    for budget in budgets.into_iter().filter(|budget| budget.enabled) {
        let status = build_budget_status(conn, &budget)?;
        let trailing_days = forecast_trailing_days(&budget.period);
        let average_daily_spend =
            budget_trailing_average_daily_spend(conn, &budget, trailing_days)?;
        let period_days = match budget.period.as_str() {
            "daily" => 1.0,
            "weekly" => 7.0,
            _ => 30.0,
        };
        let projected_period_spend = average_daily_spend * period_days;
        let remaining_budget = budget.threshold_usd - status.current_spend;
        let days_until_threshold = if status.is_over || average_daily_spend <= 0.0 {
            None
        } else {
            Some(remaining_budget / average_daily_spend)
        };

        forecasts.push(BudgetForecast {
            budget_id: budget.id,
            budget_name: budget.name,
            period: budget.period,
            provider_filter: budget.provider_filter,
            scope_kind: budget.scope_kind,
            scope_value: budget.scope_value,
            current_spend: status.current_spend,
            threshold_usd: budget.threshold_usd,
            trailing_days,
            average_daily_spend,
            projected_period_spend,
            remaining_budget,
            days_until_threshold,
            is_over: status.is_over,
        });
    }

    Ok(forecasts)
}

pub fn count_pricing(conn: &Connection) -> Result<u32> {
    conn.query_row("SELECT COUNT(*) FROM pricing", [], |row| row.get(0))
}

pub fn cleanup_old_requests(conn: &Connection, retention: &str) -> Result<usize> {
    let interval = match retention {
        "30d" => "-30 days",
        "90d" => "-90 days",
        "1y" => "-365 days",
        _ => return Ok(0), // "forever" or unknown — skip
    };
    let n = conn.execute(
        &format!(
            "DELETE FROM requests WHERE timestamp < datetime('now', '{}')",
            interval
        ),
        [],
    )?;
    Ok(n)
}

pub fn get_model_breakdown(conn: &Connection, days: u32) -> Result<Vec<ModelStats>> {
    let mut stmt = conn.prepare(
        "SELECT
            model,
            provider,
            SUM(cost_usd) as total_cost,
            COUNT(*) as total_requests,
            SUM(input_tokens + output_tokens) as total_tokens
         FROM requests
         WHERE timestamp >= datetime('now', ?1)
         GROUP BY model, provider
         ORDER BY total_cost DESC",
    )?;

    let days_param = format!("-{} days", days);
    let records = stmt
        .query_map(params![days_param], |row| {
            Ok(ModelStats {
                model: row.get(0)?,
                provider: row.get(1)?,
                total_cost: row.get(2)?,
                total_requests: row.get(3)?,
                total_tokens: row.get(4)?,
            })
        })?
        .collect::<Result<Vec<_>>>()?;

    Ok(records)
}

pub fn get_context_audit_snapshot(
    conn: &Connection,
    time_range: &str,
) -> Result<ContextAuditSnapshot> {
    let where_clause = time_range_filter(time_range);
    let api_where = if where_clause.is_empty() {
        "WHERE COALESCE(provider_type, 'api') = 'api'".to_string()
    } else {
        format!("{} AND COALESCE(provider_type, 'api') = 'api'", where_clause)
    };

    let mut findings: Vec<ContextAuditFinding> = Vec::new();
    let mut estimated_savings = 0.0_f64;

    let overprompt_filter = format!(
        "{} AND input_tokens > 2000 AND output_tokens < 100",
        api_where
    );
    let overprompt: (i64, f64, i64, i64, i64, i64) = conn.query_row(
        &format!(
            "SELECT
                COUNT(*) as cnt,
                COALESCE(SUM(cost_usd), 0.0) as cost,
                MAX(input_tokens) as max_input_tokens,
                MIN(output_tokens) as min_output_tokens,
                SUM(CASE WHEN input_tokens > 4000 AND output_tokens < 80 THEN 1 ELSE 0 END) as strict_count,
                SUM(CASE WHEN input_tokens > 2500 AND output_tokens < 120 THEN 1 ELSE 0 END) as moderate_count
             FROM requests {}",
            overprompt_filter
        ),
        [],
        |row| {
            Ok((
                row.get(0)?,
                row.get(1)?,
                row.get::<_, Option<i64>>(2)?.unwrap_or(0),
                row.get::<_, Option<i64>>(3)?.unwrap_or(0),
                row.get::<_, Option<i64>>(4)?.unwrap_or(0),
                row.get::<_, Option<i64>>(5)?.unwrap_or(0),
            ))
        },
    )?;
    if overprompt.0 > 0 {
        let top = fetch_top_occurrence(conn, &overprompt_filter)?;
        let confidence = if overprompt.4 >= 5 {
            "high"
        } else if overprompt.5 > 0 {
            "medium"
        } else {
            "low"
        };
        estimated_savings += overprompt.1;
        findings.push(ContextAuditFinding {
            key: "overprompting".to_string(),
            title: "Likely over-prompting".to_string(),
            category: "waste".to_string(),
            severity: if overprompt.4 >= 5 {
                "high"
            } else if overprompt.0 >= 5 {
                "medium"
            } else {
                "low"
            }
            .to_string(),
            confidence: confidence.to_string(),
            summary: format!(
                "{} request(s) used large prompts but returned very small outputs. This is a likely waste signal, but it can also reflect setup-heavy workflows or prompts that should be preprocessed first.",
                overprompt.0
            ),
            requests: overprompt.0,
            estimated_cost_impact_usd: overprompt.1,
            top_model: top.model.clone(),
            top_provider: top.provider.clone(),
            filter_hint: filter_hint_for(
                "overprompting",
                overprompt.0,
                top.model.as_deref(),
                top.provider.as_deref(),
            ),
            impact_label: "partial".to_string(),
            recommendation: "Trim repeated prompt scaffolding, preprocess raw material before reasoning, and re-check whether these jobs need a fresh large context each time.".to_string(),
        });
    }

    let expensive_small_filter = format!(
        "{} AND lower(model) IN ('claude-opus-4-6','gpt-4o','gpt-4.1','o1') AND (input_tokens + output_tokens) <= 1200",
        api_where
    );
    let expensive_small_work: (i64, f64) = conn.query_row(
        &format!(
            "SELECT COUNT(*) as cnt, COALESCE(SUM(cost_usd), 0.0) as cost FROM requests {}",
            expensive_small_filter
        ),
        [],
        |row| Ok((row.get(0)?, row.get(1)?)),
    )?;
    if expensive_small_work.0 > 0 {
        let top = fetch_top_occurrence(conn, &expensive_small_filter)?;
        let impact = expensive_small_work.1 * 0.5;
        estimated_savings += impact;
        findings.push(ContextAuditFinding {
            key: "premium_small_tasks".to_string(),
            title: "Possible downgrade candidates on premium models".to_string(),
            category: "opportunity".to_string(),
            severity: if expensive_small_work.0 >= 18 {
                "medium"
            } else {
                "low"
            }
            .to_string(),
            confidence: if expensive_small_work.0 >= 12 {
                "medium"
            } else {
                "low"
            }
            .to_string(),
            summary: format!(
                "{} small request(s) hit premium models. Some may be fully justified, but this pattern is a possible routing optimization for formatting, extraction, or simple transforms.",
                expensive_small_work.0
            ),
            requests: expensive_small_work.0,
            estimated_cost_impact_usd: impact,
            top_model: top.model.clone(),
            top_provider: top.provider.clone(),
            filter_hint: filter_hint_for(
                "premium_small_tasks",
                expensive_small_work.0,
                top.model.as_deref(),
                top.provider.as_deref(),
            ),
            impact_label: "heuristic".to_string(),
            recommendation: "Reserve premium models for synthesis and judgment. Test a cheaper route for repetitive transforms before treating this as confirmed waste.".to_string(),
        });
    }

    let low_cache_filter = format!(
        "{} AND input_tokens >= 4000 AND COALESCE(cached_tokens, 0) = 0",
        api_where
    );
    let low_cache_use: (i64, f64) = conn.query_row(
        &format!(
            "SELECT COUNT(*) as cnt, COALESCE(SUM(cost_usd), 0.0) as cost FROM requests {}",
            low_cache_filter
        ),
        [],
        |row| Ok((row.get(0)?, row.get(1)?)),
    )?;
    if low_cache_use.0 > 0 {
        let top = fetch_top_occurrence(conn, &low_cache_filter)?;
        let same_route_dominates =
            top.model_count * 2 >= low_cache_use.0 && top.provider_count * 2 >= low_cache_use.0;
        let confidence = if low_cache_use.0 >= 8 && same_route_dominates {
            "high"
        } else if low_cache_use.0 >= 4 {
            "medium"
        } else {
            "low"
        };
        let impact = low_cache_use.1 * 0.35;
        estimated_savings += impact;
        findings.push(ContextAuditFinding {
            key: "cache_underuse".to_string(),
            title: "Repeated heavy context without cache benefit".to_string(),
            category: "waste".to_string(),
            severity: if low_cache_use.0 >= 8 {
                "high"
            } else if low_cache_use.0 >= 4 {
                "medium"
            } else {
                "low"
            }
            .to_string(),
            confidence: confidence.to_string(),
            summary: format!(
                "{} request(s) carried 4K+ input tokens with no cache signal. That often means stable prompt or reference material is being resent, although some providers and paths may not expose cache stats consistently.",
                low_cache_use.0
            ),
            requests: low_cache_use.0,
            estimated_cost_impact_usd: impact,
            top_model: top.model.clone(),
            top_provider: top.provider.clone(),
            filter_hint: filter_hint_for(
                "cache_underuse",
                low_cache_use.0,
                top.model.as_deref(),
                top.provider.as_deref(),
            ),
            impact_label: "partial".to_string(),
            recommendation: "Cache stable system prompts, tool definitions, and recurring references where the provider supports it. If cache reporting is unavailable on this path, treat this as a prompt-hygiene check instead.".to_string(),
        });
    }

    let failed_filter = format!("{} AND COALESCE(error_message, '') != ''", api_where);
    let failed_spend: (i64, f64) = conn.query_row(
        &format!(
            "SELECT COUNT(*) as cnt, COALESCE(SUM(cost_usd), 0.0) as cost FROM requests {}",
            failed_filter
        ),
        [],
        |row| Ok((row.get(0)?, row.get(1)?)),
    )?;
    if failed_spend.0 > 0 && failed_spend.1 > 0.0 {
        let top = fetch_top_occurrence(conn, &failed_filter)?;
        estimated_savings += failed_spend.1;
        findings.push(ContextAuditFinding {
            key: "failed_requests".to_string(),
            title: "Failed paid requests are burning spend".to_string(),
            category: "waste".to_string(),
            severity: if failed_spend.1 >= 1.0 { "high" } else { "medium" }.to_string(),
            confidence: "high".to_string(),
            summary: format!(
                "{} failed request(s) still consumed about ${:.2} in paid traffic. This is a direct waste signal rather than a routing guess.",
                failed_spend.0, failed_spend.1
            ),
            requests: failed_spend.0,
            estimated_cost_impact_usd: failed_spend.1,
            top_model: top.model.clone(),
            top_provider: top.provider.clone(),
            filter_hint: filter_hint_for(
                "failed_requests",
                failed_spend.0,
                top.model.as_deref(),
                top.provider.as_deref(),
            ),
            impact_label: "direct".to_string(),
            recommendation: "Tighten upstream health checks, add retries only where they reduce paid failures, and route sensitive traffic away from unstable providers or models.".to_string(),
        });
    }

    let small_api_filter = format!("{} AND (input_tokens + output_tokens) < 500", api_where);
    let small_api_local: (i64, f64) = conn.query_row(
        &format!(
            "SELECT COUNT(*) as cnt, COALESCE(SUM(cost_usd), 0.0) as cost FROM requests {}",
            small_api_filter
        ),
        [],
        |row| Ok((row.get(0)?, row.get(1)?)),
    )?;
    if small_api_local.0 >= 10 {
        let top = fetch_top_occurrence(conn, &small_api_filter)?;
        let impact = small_api_local.1 * 0.4;
        estimated_savings += impact;
        findings.push(ContextAuditFinding {
            key: "local_model_opportunity".to_string(),
            title: "Candidate for local or budget routing".to_string(),
            category: "opportunity".to_string(),
            severity: "low".to_string(),
            confidence: if small_api_local.0 >= 20 {
                "medium"
            } else {
                "low"
            }
            .to_string(),
            summary: format!(
                "{} small API request(s) fell under 500 total tokens. Many may fit a local or budget-tier route, but latency and reliability requirements can still justify paid API usage.",
                small_api_local.0
            ),
            requests: small_api_local.0,
            estimated_cost_impact_usd: impact,
            top_model: top.model.clone(),
            top_provider: top.provider.clone(),
            filter_hint: filter_hint_for(
                "local_model_opportunity",
                small_api_local.0,
                top.model.as_deref(),
                top.provider.as_deref(),
            ),
            impact_label: "heuristic".to_string(),
            recommendation: "Route lightweight transforms, extraction cleanup, tagging, and simple formatting to a local or budget lane first, then escalate only when quality or reliability requires it.".to_string(),
        });
    }

    findings.sort_by(|a, b| {
        b.estimated_cost_impact_usd
            .partial_cmp(&a.estimated_cost_impact_usd)
            .unwrap_or(std::cmp::Ordering::Equal)
            .then_with(|| b.requests.cmp(&a.requests))
    });

    let total_penalty: f64 = findings
        .iter()
        .map(|finding| {
            context_audit_score_penalty(
                &finding.severity,
                &finding.confidence,
                finding.estimated_cost_impact_usd,
                finding.requests,
            )
        })
        .sum();
    let score = (100.0 - total_penalty).clamp(0.0, 100.0).round() as i64;
    let high_confidence_count = findings
        .iter()
        .filter(|finding| finding.confidence == "high")
        .count() as i64;
    let waste_findings_count = findings
        .iter()
        .filter(|finding| finding.category == "waste")
        .count() as i64;
    let opportunity_findings_count = findings
        .iter()
        .filter(|finding| finding.category == "opportunity")
        .count() as i64;

    Ok(ContextAuditSnapshot {
        range: time_range.to_string(),
        score,
        estimated_savings_usd: (estimated_savings * 100.0).round() / 100.0,
        high_confidence_count,
        waste_findings_count,
        opportunity_findings_count,
        findings,
    })
}

pub fn get_reliability_snapshot(
    conn: &Connection,
    time_range: &str,
) -> Result<ReliabilitySnapshot> {
    let where_clause = time_range_filter(time_range);
    let summary_query = format!(
        "SELECT
            COUNT(*) as total_requests,
            SUM(CASE WHEN COALESCE(error_message, '') = '' THEN 1 ELSE 0 END) as successful_requests,
            SUM(CASE WHEN COALESCE(error_message, '') != '' THEN 1 ELSE 0 END) as failed_requests,
            AVG(COALESCE(latency_ms, 0)) as avg_latency_ms,
            SUM(CASE WHEN COALESCE(latency_ms, 0) >= 5000 THEN 1 ELSE 0 END) as slow_requests
         FROM requests {}",
        where_clause
    );

    let summary = conn.query_row(&summary_query, [], |row| {
        let total_requests: i64 = row.get(0)?;
        let successful_requests: i64 = row.get::<_, Option<i64>>(1)?.unwrap_or(0);
        let failed_requests: i64 = row.get::<_, Option<i64>>(2)?.unwrap_or(0);
        let avg_latency_ms: f64 = row.get::<_, Option<f64>>(3)?.unwrap_or(0.0);
        let slow_requests: i64 = row.get::<_, Option<i64>>(4)?.unwrap_or(0);
        let success_rate_pct = if total_requests > 0 {
            (successful_requests as f64 / total_requests as f64) * 100.0
        } else {
            100.0
        };
        let slow_request_pct = if total_requests > 0 {
            (slow_requests as f64 / total_requests as f64) * 100.0
        } else {
            0.0
        };

        Ok(ReliabilitySummary {
            total_requests,
            successful_requests,
            failed_requests,
            success_rate_pct,
            avg_latency_ms,
            slow_requests,
            slow_request_pct,
        })
    })?;

    let provider_query = format!(
        "SELECT
            provider,
            model,
            COUNT(*) as total_requests,
            SUM(CASE WHEN COALESCE(error_message, '') != '' THEN 1 ELSE 0 END) as failed_requests,
            AVG(COALESCE(latency_ms, 0)) as avg_latency_ms,
            MAX(COALESCE(latency_ms, 0)) as max_latency_ms
         FROM requests {}
         GROUP BY provider, model
         HAVING COUNT(*) > 0
         ORDER BY total_requests DESC, avg_latency_ms DESC
         LIMIT 12",
        where_clause
    );

    let mut stmt = conn.prepare(&provider_query)?;
    let providers = stmt
        .query_map([], |row| {
            let total_requests: i64 = row.get(2)?;
            let failed_requests: i64 = row.get::<_, Option<i64>>(3)?.unwrap_or(0);
            let success_rate_pct = if total_requests > 0 {
                ((total_requests - failed_requests) as f64 / total_requests as f64) * 100.0
            } else {
                100.0
            };

            Ok(ProviderReliabilityStat {
                provider: row.get(0)?,
                model: row.get(1)?,
                total_requests,
                failed_requests,
                success_rate_pct,
                avg_latency_ms: row.get::<_, Option<f64>>(4)?.unwrap_or(0.0),
                max_latency_ms: row.get::<_, Option<i64>>(5)?.unwrap_or(0),
            })
        })?
        .collect::<Result<Vec<_>>>()?;

    let anomaly_query = "
        WITH recent AS (
            SELECT
                provider,
                model,
                COUNT(*) as recent_requests,
                AVG(COALESCE(latency_ms, 0)) as recent_avg_latency,
                1.0 * SUM(CASE WHEN COALESCE(error_message, '') != '' THEN 1 ELSE 0 END) / COUNT(*) as recent_error_rate,
                COALESCE(SUM(cost_usd), 0.0) as recent_cost
            FROM requests
            WHERE timestamp >= datetime('now', '-24 hours')
            GROUP BY provider, model
            HAVING COUNT(*) >= 5
        ),
        baseline AS (
            SELECT
                provider,
                model,
                COUNT(*) as baseline_requests,
                AVG(COALESCE(latency_ms, 0)) as baseline_avg_latency,
                1.0 * SUM(CASE WHEN COALESCE(error_message, '') != '' THEN 1 ELSE 0 END) / COUNT(*) as baseline_error_rate
            FROM requests
            WHERE timestamp >= datetime('now', '-8 days')
              AND timestamp < datetime('now', '-24 hours')
            GROUP BY provider, model
            HAVING COUNT(*) >= 10
        )
        SELECT
            recent.provider,
            recent.model,
            recent.recent_requests,
            baseline.baseline_requests,
            recent.recent_avg_latency,
            baseline.baseline_avg_latency,
            recent.recent_error_rate,
            baseline.baseline_error_rate,
            recent.recent_cost
        FROM recent
        JOIN baseline
          ON recent.provider = baseline.provider AND recent.model = baseline.model
    ";

    let mut anomaly_stmt = conn.prepare(anomaly_query)?;
    let anomaly_rows = anomaly_stmt.query_map([], |row| {
        Ok((
            row.get::<_, String>(0)?,
            row.get::<_, String>(1)?,
            row.get::<_, i64>(2)?,
            row.get::<_, i64>(3)?,
            row.get::<_, Option<f64>>(4)?.unwrap_or(0.0),
            row.get::<_, Option<f64>>(5)?.unwrap_or(0.0),
            row.get::<_, Option<f64>>(6)?.unwrap_or(0.0),
            row.get::<_, Option<f64>>(7)?.unwrap_or(0.0),
            row.get::<_, Option<f64>>(8)?.unwrap_or(0.0),
        ))
    })?;

    let mut anomalies = Vec::new();
    for row in anomaly_rows {
        let (
            provider,
            model,
            recent_requests,
            baseline_requests,
            recent_latency,
            baseline_latency,
            recent_error_rate,
            baseline_error_rate,
            recent_cost,
        ) = row?;

        if baseline_latency > 0.0
            && recent_latency > baseline_latency * 1.5
            && (recent_latency - baseline_latency) >= 250.0
        {
            let severity = if recent_latency > baseline_latency * 2.0 {
                "high"
            } else {
                "medium"
            };
            let (recommendation, fallback_model) =
                reliability_recommendation("latency_spike", &model);
            anomalies.push(ReliabilityAnomaly {
                kind: "latency_spike".to_string(),
                provider: provider.clone(),
                model: model.clone(),
                severity: severity.to_string(),
                summary: format!(
                    "Latency jumped from {:.0}ms to {:.0}ms in the last 24h",
                    baseline_latency, recent_latency
                ),
                recent_requests,
                baseline_requests,
                recent_value: recent_latency,
                baseline_value: baseline_latency,
                recent_cost,
                delta_pct: ((recent_latency - baseline_latency) / baseline_latency) * 100.0,
                recommendation,
                fallback_model,
            });
        }

        if recent_error_rate >= 0.10 && recent_error_rate > baseline_error_rate + 0.05 {
            let severity = if recent_error_rate >= 0.25 {
                "high"
            } else {
                "medium"
            };
            let (recommendation, fallback_model) =
                reliability_recommendation("error_spike", &model);
            anomalies.push(ReliabilityAnomaly {
                kind: "error_spike".to_string(),
                provider: provider.clone(),
                model: model.clone(),
                severity: severity.to_string(),
                summary: format!(
                    "Error rate rose from {:.1}% to {:.1}% in the last 24h",
                    baseline_error_rate * 100.0,
                    recent_error_rate * 100.0
                ),
                recent_requests,
                baseline_requests,
                recent_value: recent_error_rate * 100.0,
                baseline_value: baseline_error_rate * 100.0,
                recent_cost,
                delta_pct: (recent_error_rate - baseline_error_rate) * 100.0,
                recommendation,
                fallback_model,
            });
        }
    }

    anomalies.sort_by(|a, b| {
        (
            match b.severity.as_str() {
                "high" => 2,
                _ => 1,
            },
            b.recent_cost as i64,
        )
            .cmp(&(
                match a.severity.as_str() {
                    "high" => 2,
                    _ => 1,
                },
                a.recent_cost as i64,
            ))
            .then_with(|| {
                b.recent_value
                    .partial_cmp(&a.recent_value)
                    .unwrap_or(std::cmp::Ordering::Equal)
            })
    });
    anomalies.truncate(8);

    Ok(ReliabilitySnapshot {
        range: time_range.to_string(),
        summary,
        providers,
        anomalies,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn reliability_snapshot_detects_latency_and_error_spikes() {
        let db_path = std::env::temp_dir().join(format!(
            "tokenpulse-reliability-test-{}.db",
            std::process::id()
        ));
        let conn = init_db(db_path.to_str().unwrap()).unwrap();

        for day_offset in 2..8 {
            conn.execute(
                "INSERT INTO requests (timestamp, provider, model, input_tokens, output_tokens, cached_tokens, reasoning_tokens, cost_usd, latency_ms, tokens_per_second, time_to_first_token_ms, is_streaming, is_complete, source_tag, error_message, provider_type) VALUES (datetime('now', ?1), 'openai', 'gpt-4o', 100, 50, 0, 0, 0.25, 900, 0.0, 0, 0, 1, 'tests', NULL, 'api')",
                params![format!("-{} days", day_offset)],
            ).unwrap();
            conn.execute(
                "INSERT INTO requests (timestamp, provider, model, input_tokens, output_tokens, cached_tokens, reasoning_tokens, cost_usd, latency_ms, tokens_per_second, time_to_first_token_ms, is_streaming, is_complete, source_tag, error_message, provider_type) VALUES (datetime('now', ?1), 'openai', 'gpt-4o', 100, 50, 0, 0, 0.25, 950, 0.0, 0, 0, 1, 'tests', NULL, 'api')",
                params![format!("-{} days", day_offset)],
            ).unwrap();
        }

        for hour_offset in 0..6 {
            conn.execute(
                "INSERT INTO requests (timestamp, provider, model, input_tokens, output_tokens, cached_tokens, reasoning_tokens, cost_usd, latency_ms, tokens_per_second, time_to_first_token_ms, is_streaming, is_complete, source_tag, error_message, provider_type) VALUES (datetime('now', ?1), 'openai', 'gpt-4o', 100, 50, 0, 0, 0.25, 2600, 0.0, 0, 0, ?2, 'tests', ?3, 'api')",
                params![
                    format!("-{} hours", hour_offset),
                    if hour_offset < 2 { 0 } else { 1 },
                    if hour_offset < 2 { Some("upstream 500") } else { Option::<&str>::None },
                ],
            ).unwrap();
        }

        let snapshot = get_reliability_snapshot(&conn, "all").unwrap();
        assert_eq!(snapshot.summary.total_requests, 18);
        assert_eq!(snapshot.summary.failed_requests, 2);
        assert!(snapshot.anomalies.iter().any(|a| a.kind == "latency_spike"));
        assert!(snapshot.anomalies.iter().any(|a| a.kind == "error_spike"));
        let latency = snapshot
            .anomalies
            .iter()
            .find(|a| a.kind == "latency_spike")
            .unwrap();
        assert_eq!(latency.fallback_model.as_deref(), Some("gpt-4o-mini"));
        assert!(latency.recommendation.contains("gpt-4o-mini"));
        assert!(latency.recent_cost > 0.0);

        drop(conn);
        let _ = std::fs::remove_file(db_path);
    }

    #[test]
    fn budget_editing_and_alert_lifecycle_reset_cleanly() {
        let db_path = std::env::temp_dir().join(format!(
            "tokenpulse-budget-alert-test-{}-{}.db",
            std::process::id(),
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        let conn = init_db(db_path.to_str().unwrap()).unwrap();

        conn.execute(
            "INSERT INTO requests (timestamp, provider, model, input_tokens, output_tokens, cached_tokens, reasoning_tokens, cost_usd, latency_ms, tokens_per_second, time_to_first_token_ms, is_streaming, is_complete, source_tag, error_message, provider_type)
             VALUES (datetime('now', '-1 hour'), 'openai', 'gpt-4o', 100, 50, 0, 0, 6.00, 800, 0.0, 0, 0, 1, 'project-a', NULL, 'api')",
            [],
        ).unwrap();

        let budget_id = create_budget(
            &conn,
            "Project A",
            "monthly",
            5.0,
            Some("openai"),
            Some("source_tag"),
            Some("project-a"),
        )
        .unwrap();

        let triggered = sync_budget_alerts(&conn).unwrap();
        assert_eq!(triggered.len(), 1);
        assert_eq!(triggered[0].id, budget_id);
        assert!(triggered[0].alert_active);

        let statuses = check_budgets(&conn).unwrap();
        assert_eq!(statuses.len(), 1);
        assert!(statuses[0].alert_active);
        assert!(statuses[0].is_over);
        assert_eq!(statuses[0].warning_tier_pct, Some(100));

        update_budget(
            &conn,
            budget_id,
            "Project A relaxed",
            "monthly",
            10.0,
            Some("openai"),
            Some("source_tag"),
            Some("project-a"),
            true,
        )
        .unwrap();

        let statuses = check_budgets(&conn).unwrap();
        assert_eq!(statuses[0].name, "Project A relaxed");
        assert!(!statuses[0].is_over);
        assert!(!statuses[0].alert_active);

        update_budget(
            &conn,
            budget_id,
            "All Anthropic",
            "monthly",
            1.0,
            Some("anthropic"),
            Some("global"),
            None,
            true,
        )
        .unwrap();

        let statuses = check_budgets(&conn).unwrap();
        assert_eq!(statuses[0].provider_filter.as_deref(), Some("anthropic"));
        assert_eq!(statuses[0].scope_kind, "global");
        assert_eq!(statuses[0].scope_value, None);
        assert_eq!(statuses[0].current_spend, 0.0);

        set_budget_enabled(&conn, budget_id, false).unwrap();
        let statuses = check_budgets(&conn).unwrap();
        assert!(statuses.is_empty());

        drop(conn);
        let _ = std::fs::remove_file(db_path);
    }

    #[test]
    fn budget_warning_tiers_and_notifications_dedupe_cleanly() {
        let db_path = std::env::temp_dir().join(format!(
            "tokenpulse-budget-warning-test-{}-{}.db",
            std::process::id(),
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        let conn = init_db(db_path.to_str().unwrap()).unwrap();

        conn.execute(
            "INSERT INTO requests (timestamp, provider, model, input_tokens, output_tokens, cached_tokens, reasoning_tokens, cost_usd, latency_ms, tokens_per_second, time_to_first_token_ms, is_streaming, is_complete, source_tag, error_message, provider_type)
             VALUES (datetime('now', '-1 hour'), 'openai', 'gpt-4o', 100, 50, 0, 0, 8.20, 800, 0.0, 0, 0, 1, 'project-a', NULL, 'api')",
            [],
        ).unwrap();

        let budget_id = create_budget(&conn, "Warn me", "monthly", 10.0, None, None, None).unwrap();
        let statuses = check_budgets(&conn).unwrap();
        assert_eq!(statuses[0].warning_tier_pct, Some(80));

        let first = sync_budget_notifications(&conn).unwrap();
        assert_eq!(first.len(), 1);
        assert!(first[0].title.contains("80%"));

        let second = sync_budget_notifications(&conn).unwrap();
        assert!(second.is_empty());

        conn.execute(
            "UPDATE requests SET cost_usd = 9.60 WHERE source_tag = 'project-a'",
            [],
        )
        .unwrap();
        let statuses = check_budgets(&conn).unwrap();
        assert_eq!(statuses[0].warning_tier_pct, Some(95));
        let escalated = sync_budget_notifications(&conn).unwrap();
        assert_eq!(escalated.len(), 1);
        assert!(escalated[0].title.contains("95%"));

        conn.execute(
            "UPDATE requests SET cost_usd = 2.00 WHERE source_tag = 'project-a'",
            [],
        )
        .unwrap();
        let statuses = check_budgets(&conn).unwrap();
        assert_eq!(statuses[0].warning_tier_pct, None);
        sync_budget_notifications(&conn).unwrap();
        let unresolved: i64 = conn.query_row(
            "SELECT COUNT(*) FROM notifications WHERE dedupe_key LIKE 'budget:%' AND resolved_at IS NULL",
            [],
            |row| row.get(0),
        ).unwrap();
        assert_eq!(unresolved, 0);

        delete_budget(&conn, budget_id).unwrap();
        drop(conn);
        let _ = std::fs::remove_file(db_path);
    }

    #[test]
    fn reliability_notifications_are_created_once_and_marked_delivered() {
        let db_path = std::env::temp_dir().join(format!(
            "tokenpulse-reliability-notify-test-{}-{}.db",
            std::process::id(),
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        let conn = init_db(db_path.to_str().unwrap()).unwrap();

        for day_offset in 2..8 {
            conn.execute(
                "INSERT INTO requests (timestamp, provider, model, input_tokens, output_tokens, cached_tokens, reasoning_tokens, cost_usd, latency_ms, tokens_per_second, time_to_first_token_ms, is_streaming, is_complete, source_tag, error_message, provider_type) VALUES (datetime('now', ?1), 'openai', 'gpt-4o', 100, 50, 0, 0, 0.25, 900, 0.0, 0, 0, 1, 'tests', NULL, 'api')",
                params![format!("-{} days", day_offset)],
            ).unwrap();
            conn.execute(
                "INSERT INTO requests (timestamp, provider, model, input_tokens, output_tokens, cached_tokens, reasoning_tokens, cost_usd, latency_ms, tokens_per_second, time_to_first_token_ms, is_streaming, is_complete, source_tag, error_message, provider_type) VALUES (datetime('now', ?1), 'openai', 'gpt-4o', 100, 50, 0, 0, 0.25, 950, 0.0, 0, 0, 1, 'tests', NULL, 'api')",
                params![format!("-{} days", day_offset)],
            ).unwrap();
        }
        for hour_offset in 0..6 {
            conn.execute(
                "INSERT INTO requests (timestamp, provider, model, input_tokens, output_tokens, cached_tokens, reasoning_tokens, cost_usd, latency_ms, tokens_per_second, time_to_first_token_ms, is_streaming, is_complete, source_tag, error_message, provider_type) VALUES (datetime('now', ?1), 'openai', 'gpt-4o', 100, 50, 0, 0, 0.25, 2600, 0.0, 0, 0, ?2, 'tests', ?3, 'api')",
                params![
                    format!("-{} hours", hour_offset),
                    if hour_offset < 2 { 0 } else { 1 },
                    if hour_offset < 2 { Some("upstream 500") } else { Option::<&str>::None },
                ],
            ).unwrap();
        }

        let created = sync_reliability_notifications(&conn, "all").unwrap();
        assert!(!created.is_empty());
        let undelivered = get_undelivered_notifications(&conn, 10).unwrap();
        assert_eq!(created.len(), undelivered.len());
        let ids: Vec<i64> = undelivered.iter().map(|item| item.id).collect();
        mark_notifications_delivered(&conn, &ids).unwrap();
        let after = get_undelivered_notifications(&conn, 10).unwrap();
        assert!(after.is_empty());

        let duplicate = sync_reliability_notifications(&conn, "all").unwrap();
        assert!(duplicate.is_empty());

        drop(conn);
        let _ = std::fs::remove_file(db_path);
    }

    #[test]
    fn scoped_budgets_filter_by_source_tag_and_provider() {
        let db_path = std::env::temp_dir().join(format!(
            "tokenpulse-budget-test-{}-{}.db",
            std::process::id(),
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        let conn = init_db(db_path.to_str().unwrap()).unwrap();

        conn.execute(
            "INSERT INTO requests (timestamp, provider, model, input_tokens, output_tokens, cached_tokens, reasoning_tokens, cost_usd, latency_ms, tokens_per_second, time_to_first_token_ms, is_streaming, is_complete, source_tag, error_message, provider_type)
             VALUES (datetime('now', '-1 hour'), 'openai', 'gpt-4o', 100, 50, 0, 0, 1.50, 800, 0.0, 0, 0, 1, 'project-a', NULL, 'api')",
            [],
        ).unwrap();
        conn.execute(
            "INSERT INTO requests (timestamp, provider, model, input_tokens, output_tokens, cached_tokens, reasoning_tokens, cost_usd, latency_ms, tokens_per_second, time_to_first_token_ms, is_streaming, is_complete, source_tag, error_message, provider_type)
             VALUES (datetime('now', '-1 hour'), 'openai', 'gpt-4o-mini', 100, 50, 0, 0, 0.75, 900, 0.0, 0, 0, 1, 'project-b', NULL, 'api')",
            [],
        ).unwrap();
        conn.execute(
            "INSERT INTO requests (timestamp, provider, model, input_tokens, output_tokens, cached_tokens, reasoning_tokens, cost_usd, latency_ms, tokens_per_second, time_to_first_token_ms, is_streaming, is_complete, source_tag, error_message, provider_type)
             VALUES (datetime('now', '-1 hour'), 'anthropic', 'claude-sonnet', 100, 50, 0, 0, 2.00, 950, 0.0, 0, 0, 1, 'project-a', NULL, 'api')",
            [],
        ).unwrap();
        conn.execute(
            "INSERT INTO requests (timestamp, provider, model, input_tokens, output_tokens, cached_tokens, reasoning_tokens, cost_usd, latency_ms, tokens_per_second, time_to_first_token_ms, is_streaming, is_complete, source_tag, error_message, provider_type)
             VALUES (datetime('now', '-1 hour'), 'openai', 'gpt-4o', 100, 50, 0, 0, 99.0, 700, 0.0, 0, 0, 1, 'project-a', NULL, 'local')",
            [],
        ).unwrap();

        create_budget(
            &conn,
            "All OpenAI",
            "monthly",
            10.0,
            Some("openai"),
            None,
            None,
        )
        .unwrap();
        create_budget(
            &conn,
            "Project A",
            "monthly",
            10.0,
            None,
            Some("source_tag"),
            Some("project-a"),
        )
        .unwrap();
        create_budget(
            &conn,
            "Project A OpenAI",
            "monthly",
            10.0,
            Some("openai"),
            Some("project"),
            Some("project-a"),
        )
        .unwrap();

        let statuses = check_budgets(&conn).unwrap();
        assert_eq!(statuses.len(), 3);

        let openai_budget = statuses
            .iter()
            .find(|status| status.name == "All OpenAI")
            .unwrap();
        assert!((openai_budget.current_spend - 2.25).abs() < 0.0001);
        assert_eq!(openai_budget.scope_kind, "global");
        assert_eq!(openai_budget.scope_value, None);

        let project_budget = statuses
            .iter()
            .find(|status| status.name == "Project A")
            .unwrap();
        assert!((project_budget.current_spend - 3.50).abs() < 0.0001);
        assert_eq!(project_budget.scope_kind, "source_tag");
        assert_eq!(project_budget.scope_value.as_deref(), Some("project-a"));

        let project_provider_budget = statuses
            .iter()
            .find(|status| status.name == "Project A OpenAI")
            .unwrap();
        assert!((project_provider_budget.current_spend - 1.50).abs() < 0.0001);

        drop(conn);
        let _ = std::fs::remove_file(db_path);
    }
}
