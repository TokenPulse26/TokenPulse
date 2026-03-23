mod db;
mod proxy;
mod pricing;

use db::{DailyStats, ModelStats, RequestRecord};
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

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
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

            // Spawn proxy server
            let db_for_proxy = db_arc.clone();
            tauri::async_runtime::spawn(async move {
                proxy::start_proxy_server(db_for_proxy).await;
            });

            app.manage(DbState(db_arc));
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            get_recent_requests,
            get_daily_stats,
            get_model_breakdown,
            get_proxy_status,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
