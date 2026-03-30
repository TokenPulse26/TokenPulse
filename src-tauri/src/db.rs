use rusqlite::{Connection, Result, params};
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
}

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct ReliabilitySnapshot {
    pub range: String,
    pub summary: ReliabilitySummary,
    pub providers: Vec<ProviderReliabilityStat>,
    pub anomalies: Vec<ReliabilityAnomaly>,
}

pub fn init_db(path: &str) -> Result<Connection> {
    let conn = Connection::open(path)?;

    // Enable WAL mode for better concurrent read/write performance
    conn.execute_batch("PRAGMA journal_mode=WAL;")?;

    conn.execute_batch("
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
    ")?;

    // Migrations: add columns if they don't exist
    let _ = conn.execute("ALTER TABLE requests ADD COLUMN error_message TEXT", []);
    let _ = conn.execute("ALTER TABLE requests ADD COLUMN provider_type TEXT NOT NULL DEFAULT 'api'", []);
    let _ = conn.execute("ALTER TABLE budgets ADD COLUMN scope_kind TEXT NOT NULL DEFAULT 'global'", []);
    let _ = conn.execute("ALTER TABLE budgets ADD COLUMN scope_value TEXT", []);
    let _ = conn.execute("ALTER TABLE budget_alerts ADD COLUMN resolved_at TEXT", []);

    migrate_pricing_table(&conn)?;

    Ok(conn)
}

fn migrate_pricing_table(conn: &Connection) -> Result<()> {
    let primary_key_columns: Vec<String> = {
        let mut stmt = conn.prepare("PRAGMA table_info(pricing)")?;
        let rows = stmt.query_map([], |row| {
            Ok((
                row.get::<_, String>(1)?,
                row.get::<_, i64>(5)?,
            ))
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
         COMMIT;"
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
        provider_type: row.get::<_, Option<String>>(16)?.unwrap_or_else(|| "api".to_string()),
    })
}

pub fn get_recent_requests(conn: &Connection, limit: u32) -> Result<Vec<RequestRecord>> {
    let mut stmt = conn.prepare(
        "SELECT id, timestamp, provider, model, input_tokens, output_tokens, cached_tokens, reasoning_tokens, cost_usd, latency_ms, tokens_per_second, time_to_first_token_ms, is_streaming, is_complete, source_tag, error_message, COALESCE(provider_type, 'api')
         FROM requests ORDER BY timestamp DESC LIMIT ?1"
    )?;

    let records = stmt.query_map(params![limit], map_request_row)?
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
         ORDER BY date ASC"
    )?;

    let days_param = format!("-{} days", days);
    let records = stmt.query_map(params![days_param], |row| {
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
    let records = stmt.query_map([], map_request_row)?
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
    let records = stmt.query_map([], |row| {
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
    let records = stmt.query_map([], |row| {
        Ok(DailyProviderStat {
            date: row.get(0)?,
            provider: row.get(1)?,
            cost: row.get(2)?,
        })
    })?
    .collect::<Result<Vec<_>>>()?;
    Ok(records)
}

pub fn get_model_breakdown_for_range(conn: &Connection, time_range: &str) -> Result<Vec<ModelStats>> {
    let where_clause = time_range_filter(time_range);
    let query = format!(
        "SELECT model, provider, SUM(cost_usd), COUNT(*), SUM(input_tokens + output_tokens)
         FROM requests {} GROUP BY model, provider ORDER BY SUM(cost_usd) DESC",
        where_clause
    );
    let mut stmt = conn.prepare(&query)?;
    let records = stmt.query_map([], |row| {
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

pub fn get_requests_for_range(conn: &Connection, limit: u32, time_range: &str) -> Result<Vec<RequestRecord>> {
    let where_clause = time_range_filter(time_range);
    let query = format!(
        "SELECT id, timestamp, provider, model, input_tokens, output_tokens, cached_tokens, reasoning_tokens, cost_usd, latency_ms, tokens_per_second, time_to_first_token_ms, is_streaming, is_complete, source_tag, error_message, COALESCE(provider_type, 'api')
         FROM requests {} ORDER BY timestamp DESC LIMIT {}",
        where_clause, limit
    );
    let mut stmt = conn.prepare(&query)?;
    let records = stmt.query_map([], map_request_row)?
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

fn budget_current_spend(conn: &Connection, budget: &Budget) -> Result<f64> {
    let time_expr = budget_time_expr(&budget.period);

    match (
        budget.provider_filter.as_deref(),
        budget.scope_kind.as_str(),
        budget.scope_value.as_deref(),
    ) {
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
        params![name, period, threshold, provider_filter, scope_kind, scope_value, enabled as i64, id],
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
    conn.execute("DELETE FROM budget_alerts WHERE budget_id = ?1", params![id])?;
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

pub fn record_alert(conn: &Connection, budget_id: i64, current_spend: f64, threshold: f64) -> Result<()> {
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
            triggered.last_alert_triggered_at = Some(chrono::Utc::now().naive_utc().format("%Y-%m-%d %H:%M:%S").to_string());
            newly_triggered.push(triggered);
        }
    }

    Ok(newly_triggered)
}


pub fn get_budget_alert_history(conn: &Connection, limit: i64) -> Result<Vec<BudgetAlertHistoryItem>> {
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

fn budget_trailing_average_daily_spend(conn: &Connection, budget: &Budget, trailing_days: i64) -> Result<f64> {
    let time_expr = format!("datetime('now', '-{} days')", trailing_days.max(1));

    let total_spend: f64 = match (
        budget.provider_filter.as_deref(),
        budget.scope_kind.as_str(),
        budget.scope_value.as_deref(),
    ) {
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
    }?;

    Ok(total_spend / trailing_days.max(1) as f64)
}

pub fn get_budget_forecasts(conn: &Connection) -> Result<Vec<BudgetForecast>> {
    let budgets = get_budgets(conn)?;
    let mut forecasts = Vec::new();

    for budget in budgets.into_iter().filter(|budget| budget.enabled) {
        let status = build_budget_status(conn, &budget)?;
        let trailing_days = forecast_trailing_days(&budget.period);
        let average_daily_spend = budget_trailing_average_daily_spend(conn, &budget, trailing_days)?;
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
        &format!("DELETE FROM requests WHERE timestamp < datetime('now', '{}')", interval),
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
         ORDER BY total_cost DESC"
    )?;

    let days_param = format!("-{} days", days);
    let records = stmt.query_map(params![days_param], |row| {
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


pub fn get_reliability_snapshot(conn: &Connection, time_range: &str) -> Result<ReliabilitySnapshot> {
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
                1.0 * SUM(CASE WHEN COALESCE(error_message, '') != '' THEN 1 ELSE 0 END) / COUNT(*) as recent_error_rate
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
            baseline.baseline_error_rate
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
        ))
    })?;

    let mut anomalies = Vec::new();
    for row in anomaly_rows {
        let (provider, model, recent_requests, baseline_requests, recent_latency, baseline_latency, recent_error_rate, baseline_error_rate) = row?;

        if baseline_latency > 0.0
            && recent_latency > baseline_latency * 1.5
            && (recent_latency - baseline_latency) >= 250.0
        {
            let severity = if recent_latency > baseline_latency * 2.0 { "high" } else { "medium" };
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
            });
        }

        if recent_error_rate >= 0.10 && recent_error_rate > baseline_error_rate + 0.05 {
            let severity = if recent_error_rate >= 0.25 { "high" } else { "medium" };
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
            });
        }
    }

    anomalies.sort_by(|a, b| {
        b.recent_value
            .partial_cmp(&a.recent_value)
            .unwrap_or(std::cmp::Ordering::Equal)
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
        ).unwrap();

        let triggered = sync_budget_alerts(&conn).unwrap();
        assert_eq!(triggered.len(), 1);
        assert_eq!(triggered[0].id, budget_id);
        assert!(triggered[0].alert_active);

        let statuses = check_budgets(&conn).unwrap();
        assert_eq!(statuses.len(), 1);
        assert!(statuses[0].alert_active);
        assert!(statuses[0].is_over);

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
        ).unwrap();

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
        ).unwrap();

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
        ).unwrap();
        create_budget(
            &conn,
            "Project A",
            "monthly",
            10.0,
            None,
            Some("source_tag"),
            Some("project-a"),
        ).unwrap();
        create_budget(
            &conn,
            "Project A OpenAI",
            "monthly",
            10.0,
            Some("openai"),
            Some("project"),
            Some("project-a"),
        ).unwrap();

        let statuses = check_budgets(&conn).unwrap();
        assert_eq!(statuses.len(), 3);

        let openai_budget = statuses.iter().find(|status| status.name == "All OpenAI").unwrap();
        assert!((openai_budget.current_spend - 2.25).abs() < 0.0001);
        assert_eq!(openai_budget.scope_kind, "global");
        assert_eq!(openai_budget.scope_value, None);

        let project_budget = statuses.iter().find(|status| status.name == "Project A").unwrap();
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
