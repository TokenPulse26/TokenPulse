mod db;
mod proxy;
mod pricing;

use db::{Budget, BudgetStatus, CostSummary, DailyProviderStat, DailyStats, DashboardSummary, ModelStats, RequestRecord};
use std::sync::{Arc, Mutex};
use std::sync::atomic::{AtomicBool, Ordering};
use tauri::{Emitter, Manager, State};

pub struct DbState(pub Arc<Mutex<rusqlite::Connection>>);
pub struct ProxyRunningState(pub Arc<AtomicBool>);
pub struct ProxyPausedState(pub Arc<AtomicBool>);

#[tauri::command]
fn get_recent_requests(
    state: State<DbState>,
    limit: u32,
) -> Result<Vec<RequestRecord>, String> {
    let conn = state.0.lock().map_err(|e| e.to_string())?;
    db::get_recent_requests(&conn, limit).map_err(|e| e.to_string())
}

#[tauri::command]
fn get_daily_stats(
    state: State<DbState>,
    days: u32,
) -> Result<Vec<DailyStats>, String> {
    let conn = state.0.lock().map_err(|e| e.to_string())?;
    db::get_daily_stats(&conn, days).map_err(|e| e.to_string())
}

#[tauri::command]
fn get_model_breakdown(
    state: State<DbState>,
    days: u32,
) -> Result<Vec<ModelStats>, String> {
    let conn = state.0.lock().map_err(|e| e.to_string())?;
    db::get_model_breakdown(&conn, days).map_err(|e| e.to_string())
}

#[derive(serde::Serialize)]
pub struct ProxyStatus {
    running: bool,
    port: u16,
    paused: bool,
}

#[tauri::command]
fn get_proxy_status(
    running: State<ProxyRunningState>,
    paused: State<ProxyPausedState>,
) -> ProxyStatus {
    ProxyStatus {
        running: running.0.load(Ordering::SeqCst),
        port: 4100,
        paused: paused.0.load(Ordering::SeqCst),
    }
}

#[tauri::command]
fn get_setting(state: State<DbState>, key: String) -> Result<Option<String>, String> {
    let conn = state.0.lock().map_err(|e| e.to_string())?;
    db::get_setting(&conn, &key).map_err(|e| e.to_string())
}

#[tauri::command]
fn set_setting(state: State<DbState>, key: String, value: String) -> Result<(), String> {
    let conn = state.0.lock().map_err(|e| e.to_string())?;
    db::set_setting(&conn, &key, &value).map_err(|e| e.to_string())
}

#[tauri::command]
fn get_dashboard_stats(
    state: State<DbState>,
    time_range: String,
) -> Result<DashboardSummary, String> {
    let conn = state.0.lock().map_err(|e| e.to_string())?;
    db::get_summary_stats(&conn, &time_range).map_err(|e| e.to_string())
}

#[tauri::command]
fn get_daily_stats_range(
    state: State<DbState>,
    time_range: String,
) -> Result<Vec<DailyStats>, String> {
    let conn = state.0.lock().map_err(|e| e.to_string())?;
    db::get_daily_stats_for_range(&conn, &time_range).map_err(|e| e.to_string())
}

#[tauri::command]
fn get_daily_provider_stats(
    state: State<DbState>,
    time_range: String,
) -> Result<Vec<DailyProviderStat>, String> {
    let conn = state.0.lock().map_err(|e| e.to_string())?;
    db::get_daily_provider_stats_for_range(&conn, &time_range).map_err(|e| e.to_string())
}

#[tauri::command]
fn get_model_breakdown_range(
    state: State<DbState>,
    time_range: String,
) -> Result<Vec<ModelStats>, String> {
    let conn = state.0.lock().map_err(|e| e.to_string())?;
    db::get_model_breakdown_for_range(&conn, &time_range).map_err(|e| e.to_string())
}

#[tauri::command]
fn get_requests_range(
    state: State<DbState>,
    limit: u32,
    time_range: String,
) -> Result<Vec<RequestRecord>, String> {
    let conn = state.0.lock().map_err(|e| e.to_string())?;
    db::get_requests_for_range(&conn, limit, &time_range).map_err(|e| e.to_string())
}

#[tauri::command]
fn get_cost_summary(
    state: State<DbState>,
    time_range: String,
) -> Result<CostSummary, String> {
    let conn = state.0.lock().map_err(|e| e.to_string())?;
    db::get_cost_summary(&conn, &time_range).map_err(|e| e.to_string())
}

#[tauri::command]
async fn test_proxy() -> Result<bool, String> {
    let client = reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(5))
        .build()
        .map_err(|e| e.to_string())?;
    match client.get("http://localhost:4100/").send().await {
        Ok(_) => Ok(true),
        Err(e) => Err(format!("Proxy not responding: {}", e)),
    }
}

#[derive(serde::Serialize)]
pub struct PricingStatus {
    total_models: u32,
    last_updated: Option<String>,
}

#[tauri::command]
fn get_pricing_status(state: State<DbState>) -> Result<PricingStatus, String> {
    let conn = state.0.lock().map_err(|e| e.to_string())?;
    let total_models = db::count_pricing(&conn).map_err(|e| e.to_string())?;
    let last_updated = db::get_setting(&conn, "pricing_last_updated").map_err(|e| e.to_string())?;
    Ok(PricingStatus { total_models, last_updated })
}

#[tauri::command]
fn update_pricing_now(state: State<DbState>) -> Result<(), String> {
    let db = state.0.clone();
    spawn_pricing_update(db);
    Ok(())
}

fn csv_escape(value: &str) -> String {
    if value.contains([',', '"', '\n', '\r']) {
        format!("\"{}\"", value.replace('"', "\"\""))
    } else {
        value.to_string()
    }
}

#[tauri::command]
fn export_csv(app: tauri::AppHandle, state: State<DbState>) -> Result<String, String> {
    use tauri_plugin_dialog::DialogExt;

    let csv = {
        let conn = state.0.lock().map_err(|e| e.to_string())?;
        let requests = db::get_all_requests(&conn).map_err(|e| e.to_string())?;
        let mut s = String::from("timestamp,provider,model,input_tokens,output_tokens,cost_usd,latency_ms,is_streaming,error_message,cached_tokens,reasoning_tokens,tokens_per_second,time_to_first_token_ms,source_tag,provider_type\n");
        for r in &requests {
            s.push_str(&format!(
                "{},{},{},{},{},{:.6},{},{},{},{},{},{:.1},{},{},{}\n",
                csv_escape(&r.timestamp),
                csv_escape(&r.provider),
                csv_escape(&r.model),
                r.input_tokens,
                r.output_tokens,
                r.cost_usd,
                r.latency_ms,
                r.is_streaming,
                csv_escape(r.error_message.as_deref().unwrap_or("")),
                r.cached_tokens,
                r.reasoning_tokens,
                r.tokens_per_second,
                r.time_to_first_token_ms,
                csv_escape(&r.source_tag),
                csv_escape(&r.provider_type),
            ));
        }
        s
    };

    let file_path = app
        .dialog()
        .file()
        .add_filter("CSV Files", &["csv"])
        .blocking_save_file();

    match file_path {
        Some(path) => {
            let path_buf = path.into_path().map_err(|e| e.to_string())?;
            std::fs::write(&path_buf, &csv).map_err(|e| e.to_string())?;
            Ok(path_buf.to_string_lossy().to_string())
        }
        None => Err("cancelled".to_string()),
    }
}

#[tauri::command]
async fn set_autostart(app: tauri::AppHandle, enabled: bool) -> Result<(), String> {
    use tauri_plugin_autostart::ManagerExt;
    if enabled {
        app.autolaunch().enable().map_err(|e| e.to_string())?;
    } else {
        app.autolaunch().disable().map_err(|e| e.to_string())?;
    }
    Ok(())
}

#[tauri::command]
fn toggle_proxy_pause(
    paused_state: State<ProxyPausedState>,
) -> bool {
    let was_paused = paused_state.0.load(Ordering::SeqCst);
    paused_state.0.store(!was_paused, Ordering::SeqCst);
    !was_paused
}

#[derive(serde::Serialize, Clone)]
pub struct UpdateInfo {
    pub version: String,
    pub notes: String,
}

async fn check_for_update_inner(app: &tauri::AppHandle) {
    let update_url = "https://raw.githubusercontent.com/tokenpulse/tokenpulse/main/update.json";
    let client = match reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(10))
        .build()
    {
        Ok(c) => c,
        Err(_) => return,
    };

    let resp = match client.get(update_url).send().await {
        Ok(r) => r,
        Err(_) => return,
    };

    let json: serde_json::Value = match resp.json().await {
        Ok(j) => j,
        Err(_) => return,
    };

    let current_version = app.package_info().version.to_string();
    if let Some(latest) = json.get("version").and_then(|v| v.as_str()) {
        if latest != current_version && is_newer_version(latest, &current_version) {
            let notes = json
                .get("notes")
                .and_then(|v| v.as_str())
                .unwrap_or("")
                .to_string();
            let _ = app.emit("update-available", UpdateInfo { version: latest.to_string(), notes });
        }
    }
}

fn is_newer_version(latest: &str, current: &str) -> bool {
    let parse = |v: &str| -> Vec<u32> {
        v.trim_start_matches('v')
            .split('.')
            .filter_map(|p| p.parse().ok())
            .collect()
    };
    let l = parse(latest);
    let c = parse(current);
    for i in 0..l.len().max(c.len()) {
        let lv = l.get(i).copied().unwrap_or(0);
        let cv = c.get(i).copied().unwrap_or(0);
        if lv > cv { return true; }
        if lv < cv { return false; }
    }
    false
}

#[tauri::command]
async fn check_for_update(app: tauri::AppHandle) -> Result<(), String> {
    check_for_update_inner(&app).await;
    Ok(())
}

fn spawn_pricing_update(db: Arc<Mutex<rusqlite::Connection>>) {
    tauri::async_runtime::spawn(async move {
        let url = "https://raw.githubusercontent.com/BerriAI/litellm/main/model_prices_and_context_window.json";
        let client = match reqwest::Client::builder()
            .timeout(std::time::Duration::from_secs(30))
            .build()
        {
            Ok(c) => c,
            Err(_) => return,
        };

        let text = match client.get(url).send().await {
            Ok(resp) => match resp.text().await {
                Ok(t) => t,
                Err(_) => return,
            },
            Err(_) => return,
        };

        let entries = pricing::parse_litellm_json(&text);
        if entries.is_empty() {
            return;
        }

        if let Ok(conn) = db.lock() {
            for entry in &entries {
                let _ = db::upsert_pricing(
                    &conn,
                    &entry.model,
                    &entry.provider,
                    entry.input_cost_per_million,
                    entry.output_cost_per_million,
                    entry.context_window as i64,
                );
            }
            let _ = db::set_setting(
                &conn,
                "pricing_last_updated",
                &chrono::Utc::now().to_rfc3339(),
            );
        }
    });
}

// ─── Budget commands ──────────────────────────────────────────────────────────

#[tauri::command]
fn create_budget(
    state: State<DbState>,
    name: String,
    period: String,
    threshold_usd: f64,
    provider_filter: Option<String>,
    scope_kind: Option<String>,
    scope_value: Option<String>,
) -> Result<i64, String> {
    let conn = state.0.lock().map_err(|e| e.to_string())?;
    db::create_budget(
        &conn,
        &name,
        &period,
        threshold_usd,
        provider_filter.as_deref(),
        scope_kind.as_deref(),
        scope_value.as_deref(),
    )
    .map_err(|e| e.to_string())
}

#[tauri::command]
fn get_budgets(state: State<DbState>) -> Result<Vec<Budget>, String> {
    let conn = state.0.lock().map_err(|e| e.to_string())?;
    db::get_budgets(&conn).map_err(|e| e.to_string())
}

#[tauri::command]
fn update_budget(
    state: State<DbState>,
    id: i64,
    name: String,
    period: String,
    threshold_usd: f64,
    provider_filter: Option<String>,
    scope_kind: Option<String>,
    scope_value: Option<String>,
    enabled: bool,
) -> Result<(), String> {
    let conn = state.0.lock().map_err(|e| e.to_string())?;
    db::update_budget(
        &conn,
        id,
        &name,
        &period,
        threshold_usd,
        provider_filter.as_deref(),
        scope_kind.as_deref(),
        scope_value.as_deref(),
        enabled,
    )
    .map_err(|e| e.to_string())
}

#[tauri::command]
fn set_budget_enabled(state: State<DbState>, id: i64, enabled: bool) -> Result<(), String> {
    let conn = state.0.lock().map_err(|e| e.to_string())?;
    db::set_budget_enabled(&conn, id, enabled).map_err(|e| e.to_string())
}

#[tauri::command]
fn delete_budget(state: State<DbState>, id: i64) -> Result<(), String> {
    let conn = state.0.lock().map_err(|e| e.to_string())?;
    db::delete_budget(&conn, id).map_err(|e| e.to_string())
}

#[tauri::command]
fn check_budgets(state: State<DbState>) -> Result<Vec<BudgetStatus>, String> {
    let conn = state.0.lock().map_err(|e| e.to_string())?;
    db::check_budgets(&conn).map_err(|e| e.to_string())
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_clipboard_manager::init())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_autostart::init(
            tauri_plugin_autostart::MacosLauncher::LaunchAgent,
            Some(vec![]),
        ))
        .plugin(tauri_plugin_notification::init())
        .plugin(tauri_plugin_updater::Builder::new().build())
        .setup(|app| {
            let app_dir = app
                .path()
                .app_data_dir()
                .expect("Failed to get app data dir");
            std::fs::create_dir_all(&app_dir).expect("Failed to create app data dir");
            let db_path = app_dir.join("tokenpulse.db");
            let db_path_str = db_path.to_str().expect("Invalid DB path").to_string();

            let conn = db::init_db(&db_path_str).expect("Failed to initialize database");
            let db_arc = Arc::new(Mutex::new(conn));

            // Enforce data retention on startup
            if let Ok(conn) = db_arc.lock() {
                if let Ok(Some(retention)) = db::get_setting(&conn, "data_retention") {
                    let _ = db::cleanup_old_requests(&conn, &retention);
                }
            }

            let proxy_running = Arc::new(AtomicBool::new(false));
            let proxy_paused = Arc::new(AtomicBool::new(false));

            let db_for_proxy = db_arc.clone();
            let running_for_proxy = proxy_running.clone();
            let paused_for_proxy = proxy_paused.clone();
            tauri::async_runtime::spawn(async move {
                proxy::start_proxy_server(db_for_proxy, running_for_proxy, paused_for_proxy).await;
            });

            spawn_pricing_update(db_arc.clone());

            // Check for updates in the background after a short delay
            let app_handle_for_update = app.handle().clone();
            tauri::async_runtime::spawn(async move {
                tokio::time::sleep(std::time::Duration::from_secs(8)).await;
                check_for_update_inner(&app_handle_for_update).await;
            });

            app.manage(DbState(db_arc.clone()));
            app.manage(ProxyRunningState(proxy_running.clone()));
            app.manage(ProxyPausedState(proxy_paused.clone()));

            // Set up system tray
            setup_tray(app, db_arc, proxy_paused)?;

            Ok(())
        })
        // Tray-only mode: no window close interception needed.
        // The window is hidden on startup via tauri.conf.json (visible: false).
        .invoke_handler(tauri::generate_handler![
            get_recent_requests,
            get_daily_stats,
            get_model_breakdown,
            get_proxy_status,
            get_setting,
            set_setting,
            get_dashboard_stats,
            get_daily_stats_range,
            get_daily_provider_stats,
            get_model_breakdown_range,
            get_requests_range,
            test_proxy,
            get_cost_summary,
            update_pricing_now,
            get_pricing_status,
            export_csv,
            set_autostart,
            toggle_proxy_pause,
            check_for_update,
            create_budget,
            get_budgets,
            update_budget,
            set_budget_enabled,
            delete_budget,
            check_budgets,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}

fn setup_tray(
    app: &tauri::App,
    db: Arc<Mutex<rusqlite::Connection>>,
    proxy_paused: Arc<AtomicBool>,
) -> Result<(), Box<dyn std::error::Error>> {
    use tauri::menu::{Menu, MenuItem, PredefinedMenuItem};
    use tauri::tray::TrayIconBuilder;

    let today_item = MenuItem::with_id(app, "today_spend", "Today: $0.00", false, None::<&str>)?;
    let open_item = MenuItem::with_id(app, "open", "Open Dashboard", true, None::<&str>)?;
    let pause_item = MenuItem::with_id(app, "toggle_proxy", "Pause Proxy", true, None::<&str>)?;
    let quit_item = MenuItem::with_id(app, "quit", "Quit TokenPulse", true, None::<&str>)?;

    let menu = Menu::with_items(app, &[
        &today_item,
        &PredefinedMenuItem::separator(app)?,
        &open_item,
        &pause_item,
        &PredefinedMenuItem::separator(app)?,
        &quit_item,
    ])?;

    let today_item_clone = today_item.clone();
    let pause_item_clone = pause_item.clone();
    let proxy_paused_for_menu = proxy_paused.clone();

    let _tray = TrayIconBuilder::with_id("main")
        .icon(app.default_window_icon().unwrap().clone())
        .menu(&menu)
        .show_menu_on_left_click(true)
        .on_menu_event(move |app, event| {
            match event.id.as_ref() {
                "open" => {
                    // Open the web dashboard in the default browser
                    let _ = tauri::async_runtime::spawn(async {
                        let _ = open::that("http://localhost:4200");
                    });
                    let _ = app; // suppress unused warning
                }
                "toggle_proxy" => {
                    let was_paused = proxy_paused_for_menu.load(Ordering::SeqCst);
                    proxy_paused_for_menu.store(!was_paused, Ordering::SeqCst);
                    let new_label = if was_paused { "Pause Proxy" } else { "Resume Proxy" };
                    let _ = pause_item_clone.set_text(new_label);
                }
                "quit" => {
                    app.exit(0);
                }
                _ => {}
            }
        })
        .build(app)?;

    // Update "Today" spend label every 30 seconds and check budgets
    let app_handle_for_tray = app.handle().clone();
    tauri::async_runtime::spawn(async move {
        use tauri_plugin_notification::NotificationExt;
        loop {
            tokio::time::sleep(std::time::Duration::from_secs(30)).await;
            if let Ok(conn) = db.lock() {
                if let Ok(summary) = db::get_summary_stats(&conn, "today") {
                    let text = format!("Today: ${:.2}", summary.total_cost);
                    let _ = today_item_clone.set_text(text);
                }

                // Check budgets and send notifications for newly triggered alerts.
                if let Ok(triggered_alerts) = db::sync_budget_alerts(&conn) {
                    for status in &triggered_alerts {
                        let _ = app_handle_for_tray
                            .notification()
                            .builder()
                            .title("⚠ Budget Alert")
                            .body(format!(
                                "{} — ${:.2} / ${:.2}",
                                status.name,
                                status.current_spend,
                                status.threshold_usd,
                            ))
                            .show();
                    }
                }
            }
        }
    });

    Ok(())
}
