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

pub fn init_db(path: &str) -> Result<Connection> {
    let conn = Connection::open(path)?;

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
            model TEXT PRIMARY KEY,
            provider TEXT NOT NULL,
            input_cost_per_million_tokens REAL NOT NULL DEFAULT 0.0,
            output_cost_per_million_tokens REAL NOT NULL DEFAULT 0.0,
            context_window_tokens INTEGER NOT NULL DEFAULT 0,
            is_custom INTEGER NOT NULL DEFAULT 0,
            last_updated TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_requests_timestamp ON requests(timestamp);
        CREATE INDEX IF NOT EXISTS idx_requests_provider ON requests(provider);
        CREATE INDEX IF NOT EXISTS idx_requests_model ON requests(model);

        CREATE TABLE IF NOT EXISTS budgets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            period TEXT NOT NULL CHECK(period IN ('daily','weekly','monthly')),
            threshold_usd REAL NOT NULL,
            provider_filter TEXT,
            enabled INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS budget_alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            budget_id INTEGER NOT NULL,
            triggered_at TEXT NOT NULL DEFAULT (datetime('now')),
            current_spend REAL NOT NULL,
            threshold_usd REAL NOT NULL,
            FOREIGN KEY (budget_id) REFERENCES budgets(id)
        );
    ")?;

    // Migrations: add columns if they don't exist
    let _ = conn.execute("ALTER TABLE requests ADD COLUMN error_message TEXT", []);
    let _ = conn.execute("ALTER TABLE requests ADD COLUMN provider_type TEXT NOT NULL DEFAULT 'api'", []);

    Ok(conn)
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
         ON CONFLICT(model) DO UPDATE SET
             provider=excluded.provider,
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

pub fn get_price_for_model(conn: &Connection, model: &str) -> Result<Option<(f64, f64)>> {
    let model_lower = model.to_lowercase();
    let result = conn.query_row(
        "SELECT input_cost_per_million_tokens, output_cost_per_million_tokens FROM pricing WHERE lower(model) = ?1",
        params![model_lower],
        |row| Ok((row.get::<_, f64>(0)?, row.get::<_, f64>(1)?)),
    );
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
    pub enabled: bool,
    pub current_spend: f64,
    pub percentage: f64,
    pub is_over: bool,
}

// ─── Budget functions ─────────────────────────────────────────────────────────

pub fn create_budget(
    conn: &Connection,
    name: &str,
    period: &str,
    threshold: f64,
    provider_filter: Option<&str>,
) -> Result<i64> {
    conn.execute(
        "INSERT INTO budgets (name, period, threshold_usd, provider_filter, enabled, created_at)
         VALUES (?1, ?2, ?3, ?4, 1, datetime('now'))",
        params![name, period, threshold, provider_filter],
    )?;
    Ok(conn.last_insert_rowid())
}

pub fn get_budgets(conn: &Connection) -> Result<Vec<Budget>> {
    let mut stmt = conn.prepare(
        "SELECT id, name, period, threshold_usd, provider_filter, enabled, created_at
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
                enabled: row.get::<_, i64>(5)? != 0,
                created_at: row.get(6)?,
            })
        })?
        .collect::<Result<Vec<_>>>()?;
    Ok(records)
}

pub fn update_budget(conn: &Connection, id: i64, enabled: bool) -> Result<()> {
    conn.execute(
        "UPDATE budgets SET enabled = ?1 WHERE id = ?2",
        params![enabled as i64, id],
    )?;
    Ok(())
}

pub fn delete_budget(conn: &Connection, id: i64) -> Result<()> {
    conn.execute("DELETE FROM budget_alerts WHERE budget_id = ?1", params![id])?;
    conn.execute("DELETE FROM budgets WHERE id = ?1", params![id])?;
    Ok(())
}

pub fn check_budgets(conn: &Connection) -> Result<Vec<BudgetStatus>> {
    let budgets = get_budgets(conn)?;
    let mut statuses = Vec::new();

    for budget in budgets.iter().filter(|b| b.enabled) {
        let time_expr = match budget.period.as_str() {
            "daily" => "datetime('now', 'start of day')",
            "weekly" => "datetime('now', '-7 days')",
            _ => "datetime('now', '-30 days')", // monthly
        };

        let current_spend: f64 = match &budget.provider_filter {
            Some(pf) => conn.query_row(
                &format!(
                    "SELECT COALESCE(SUM(cost_usd), 0.0) FROM requests \
                     WHERE timestamp >= {} AND COALESCE(provider_type,'api') = 'api' \
                     AND provider = ?1",
                    time_expr
                ),
                params![pf],
                |row| row.get(0),
            )?,
            None => conn.query_row(
                &format!(
                    "SELECT COALESCE(SUM(cost_usd), 0.0) FROM requests \
                     WHERE timestamp >= {} AND COALESCE(provider_type,'api') = 'api'",
                    time_expr
                ),
                [],
                |row| row.get(0),
            )?,
        };

        let percentage = if budget.threshold_usd > 0.0 {
            (current_spend / budget.threshold_usd) * 100.0
        } else {
            0.0
        };

        statuses.push(BudgetStatus {
            id: budget.id,
            name: budget.name.clone(),
            period: budget.period.clone(),
            threshold_usd: budget.threshold_usd,
            provider_filter: budget.provider_filter.clone(),
            enabled: budget.enabled,
            current_spend,
            percentage,
            is_over: current_spend >= budget.threshold_usd,
        });
    }

    Ok(statuses)
}

pub fn record_alert(conn: &Connection, budget_id: i64, current_spend: f64, threshold: f64) -> Result<()> {
    conn.execute(
        "INSERT INTO budget_alerts (budget_id, triggered_at, current_spend, threshold_usd)
         VALUES (?1, datetime('now'), ?2, ?3)",
        params![budget_id, current_spend, threshold],
    )?;
    Ok(())
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
