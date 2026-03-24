mod db;
mod proxy;
mod pricing;

use db::{DailyStats, DashboardSummary, ModelStats, RequestRecord};
use std::sync::{Arc, Mutex};
use tauri::{Manager, State};

pub struct DbState(pub Arc<Mutex<rusqlite::Connection>>);

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
}

#[tauri::command]
fn get_proxy_status() -> ProxyStatus {
    ProxyStatus {
        running: true,
        port: 4100,
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

#[tauri::command]
fn update_pricing_now(state: State<DbState>) -> Result<(), String> {
    let db = state.0.clone();
    spawn_pricing_update(db);
    Ok(())
}

#[tauri::command]
fn export_csv(app: tauri::AppHandle, state: State<DbState>) -> Result<String, String> {
    use tauri_plugin_dialog::DialogExt;

    let csv = {
        let conn = state.0.lock().map_err(|e| e.to_string())?;
        let requests = db::get_all_requests(&conn).map_err(|e| e.to_string())?;
        let mut s = String::from("timestamp,provider,model,input_tokens,output_tokens,cost_usd,latency_ms\n");
        for r in &requests {
            s.push_str(&format!(
                "{},{},{},{},{},{:.6},{}\n",
                r.timestamp, r.provider, r.model,
                r.input_tokens, r.output_tokens,
                r.cost_usd, r.latency_ms
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

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_clipboard_manager::init())
        .plugin(tauri_plugin_dialog::init())
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

            let db_for_proxy = db_arc.clone();
            tauri::async_runtime::spawn(async move {
                proxy::start_proxy_server(db_for_proxy).await;
            });

            spawn_pricing_update(db_arc.clone());

            app.manage(DbState(db_arc));
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            get_recent_requests,
            get_daily_stats,
            get_model_breakdown,
            get_proxy_status,
            get_setting,
            set_setting,
            get_dashboard_stats,
            get_daily_stats_range,
            get_model_breakdown_range,
            get_requests_range,
            test_proxy,
            update_pricing_now,
            export_csv,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
