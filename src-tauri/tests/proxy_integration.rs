//! End-to-end tests for the proxy: real HTTP requests through the full
//! axum handler stack to a mock upstream, asserting on what gets forwarded
//! and what lands in the database.
//!
//! These exist because the unit tests only cover parsing helpers — every
//! production incident so far (stripped auth headers, broken SSE streaming,
//! missed Ollama NDJSON tokens) lived in the glue these tests exercise.

use std::sync::atomic::AtomicBool;
use std::sync::{Arc, Mutex};
use std::time::Duration;

use axum::body::Body;
use axum::http::{HeaderMap, Response, StatusCode};
use axum::Router;
use serde_json::{json, Value};

use tauri_app_lib::db::init_db;
use tauri_app_lib::proxy::{build_router, AppState};

/// What the mock upstream saw, captured for assertions.
#[derive(Clone, Default)]
struct CapturedRequest {
    path: String,
    headers: Vec<(String, String)>,
    body: Value,
}

type Captured = Arc<Mutex<Vec<CapturedRequest>>>;

/// Start a mock upstream that records every request and replies with a
/// fixed status / content-type / body. Returns its base URL and the capture
/// log.
async fn spawn_mock_upstream(
    status: StatusCode,
    content_type: &'static str,
    response_body: &'static str,
) -> (String, Captured) {
    let captured: Captured = Arc::new(Mutex::new(Vec::new()));
    let captured_clone = captured.clone();

    let app = Router::new().fallback(
        move |headers: HeaderMap, req: axum::http::Request<Body>| {
            let captured = captured_clone.clone();
            async move {
                let path = req.uri().path().to_string();
                let body_bytes = axum::body::to_bytes(req.into_body(), 1024 * 1024)
                    .await
                    .unwrap_or_default();
                let body: Value = serde_json::from_slice(&body_bytes).unwrap_or(Value::Null);
                captured.lock().unwrap().push(CapturedRequest {
                    path,
                    headers: headers
                        .iter()
                        .map(|(k, v)| {
                            (k.as_str().to_string(), v.to_str().unwrap_or("").to_string())
                        })
                        .collect(),
                    body,
                });
                Response::builder()
                    .status(status)
                    .header("content-type", content_type)
                    .body(Body::from(response_body))
                    .unwrap()
            }
        },
    );

    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let url = format!("http://{}", listener.local_addr().unwrap());
    tokio::spawn(async move {
        axum::serve(listener, app).await.ok();
    });
    (url, captured)
}

/// Start the real proxy router against a fresh in-memory DB, with every
/// provider route overridden to point at `upstream_url`. Returns the proxy
/// base URL and a handle to the DB for assertions.
async fn spawn_proxy(upstream_url: &str) -> (String, Arc<Mutex<rusqlite::Connection>>) {
    let conn = init_db(":memory:").expect("in-memory DB");
    let db = Arc::new(Mutex::new(conn));
    let state = AppState {
        db: db.clone(),
        http_client: reqwest::Client::new(),
        proxy_paused: Arc::new(AtomicBool::new(false)),
        upstream_override: Some(upstream_url.to_string()),
    };
    let app = build_router(state);
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let url = format!("http://{}", listener.local_addr().unwrap());
    tokio::spawn(async move {
        axum::serve(listener, app).await.ok();
    });
    (url, db)
}

#[derive(Debug, Default)]
struct StoredRequest {
    provider: String,
    model: String,
    input_tokens: i64,
    output_tokens: i64,
    cached_tokens: i64,
    cache_creation_tokens: i64,
    is_streaming: bool,
    is_complete: bool,
    error_message: Option<String>,
}

/// Streaming inserts happen on a background task after the client finishes
/// reading, so poll briefly instead of asserting immediately.
async fn wait_for_request_row(db: &Arc<Mutex<rusqlite::Connection>>) -> StoredRequest {
    for _ in 0..50 {
        {
            let conn = db.lock().unwrap();
            let row = conn.query_row(
                "SELECT provider, model, input_tokens, output_tokens, cached_tokens,
                        cache_creation_tokens, is_streaming, is_complete, error_message
                 FROM requests ORDER BY id DESC LIMIT 1",
                [],
                |row| {
                    Ok(StoredRequest {
                        provider: row.get(0)?,
                        model: row.get(1)?,
                        input_tokens: row.get(2)?,
                        output_tokens: row.get(3)?,
                        cached_tokens: row.get(4)?,
                        cache_creation_tokens: row.get(5)?,
                        is_streaming: row.get::<_, i64>(6)? != 0,
                        is_complete: row.get::<_, i64>(7)? != 0,
                        error_message: row.get(8)?,
                    })
                },
            );
            if let Ok(r) = row {
                return r;
            }
        }
        tokio::time::sleep(Duration::from_millis(50)).await;
    }
    panic!("no request row appeared in the database within 2.5s");
}

#[tokio::test]
async fn anthropic_request_forwards_headers_and_records_usage() {
    let upstream_body = r#"{
        "id": "msg_test",
        "model": "claude-sonnet-4-6",
        "usage": {
            "input_tokens": 100,
            "output_tokens": 50,
            "cache_read_input_tokens": 30,
            "cache_creation_input_tokens": 10
        }
    }"#;
    let (upstream, captured) =
        spawn_mock_upstream(StatusCode::OK, "application/json", upstream_body).await;
    let (proxy, db) = spawn_proxy(&upstream).await;

    let resp = reqwest::Client::new()
        .post(format!("{}/anthropic/v1/messages", proxy))
        .header("authorization", "Bearer test-token-123")
        .header("x-api-key", "sk-ant-test")
        .json(&json!({"model": "claude-sonnet-4-6", "messages": []}))
        .send()
        .await
        .unwrap();

    // Response passes through untouched
    assert_eq!(resp.status(), 200);
    let body: Value = resp.json().await.unwrap();
    assert_eq!(body["id"], "msg_test");

    // Upstream saw the stripped path and ALL auth headers (gotcha #2:
    // header stripping broke everything downstream once already)
    let seen = captured.lock().unwrap().first().cloned().unwrap();
    assert_eq!(seen.path, "/v1/messages");
    let header = |name: &str| {
        seen.headers
            .iter()
            .find(|(k, _)| k == name)
            .map(|(_, v)| v.clone())
    };
    assert_eq!(header("authorization").as_deref(), Some("Bearer test-token-123"));
    assert_eq!(header("x-api-key").as_deref(), Some("sk-ant-test"));

    // Tokens recorded with Anthropic semantics (input excludes cached)
    let row = wait_for_request_row(&db).await;
    assert_eq!(row.provider, "anthropic");
    assert_eq!(row.model, "claude-sonnet-4-6");
    assert_eq!(row.input_tokens, 100);
    assert_eq!(row.output_tokens, 50);
    assert_eq!(row.cached_tokens, 30);
    assert_eq!(row.cache_creation_tokens, 10);
    assert!(!row.is_streaming);
    assert!(row.is_complete);
    assert_eq!(row.error_message, None);
}

#[tokio::test]
async fn anthropic_streaming_forwards_chunks_and_captures_usage() {
    // Usage arrives split across message_start (input) and message_delta
    // (output) — the accumulator has to merge them.
    let sse_body = concat!(
        "event: message_start\n",
        "data: {\"type\":\"message_start\",\"message\":{\"usage\":{\"input_tokens\":200,\"cache_read_input_tokens\":120,\"cache_creation_input_tokens\":80}}}\n",
        "\n",
        "event: content_block_delta\n",
        "data: {\"type\":\"content_block_delta\",\"delta\":{\"text\":\"hello\"}}\n",
        "\n",
        "event: message_delta\n",
        "data: {\"type\":\"message_delta\",\"usage\":{\"output_tokens\":77}}\n",
        "\n",
        "event: message_stop\n",
        "data: {\"type\":\"message_stop\"}\n",
        "\n",
    );
    let (upstream, _captured) =
        spawn_mock_upstream(StatusCode::OK, "text/event-stream", sse_body).await;
    let (proxy, db) = spawn_proxy(&upstream).await;

    let resp = reqwest::Client::new()
        .post(format!("{}/anthropic/v1/messages", proxy))
        .json(&json!({"model": "claude-sonnet-4-6", "stream": true, "messages": []}))
        .send()
        .await
        .unwrap();
    assert_eq!(resp.status(), 200);

    // The client must receive the raw SSE stream unmodified
    let streamed = resp.text().await.unwrap();
    assert!(streamed.contains("message_start"));
    assert!(streamed.contains("\"text\":\"hello\""));
    assert!(streamed.contains("message_stop"));

    let row = wait_for_request_row(&db).await;
    assert_eq!(row.provider, "anthropic");
    assert_eq!(row.input_tokens, 200);
    assert_eq!(row.output_tokens, 77);
    assert_eq!(row.cached_tokens, 120);
    assert_eq!(row.cache_creation_tokens, 80);
    assert!(row.is_streaming);
    assert!(row.is_complete);
}

#[tokio::test]
async fn openai_compatible_stream_gets_usage_injection_and_records_tokens() {
    let sse_body = concat!(
        "data: {\"choices\":[{\"delta\":{\"content\":\"hi\"}}]}\n",
        "\n",
        "data: {\"choices\":[],\"usage\":{\"prompt_tokens\":60,\"completion_tokens\":40,\"prompt_tokens_details\":{\"cached_tokens\":20}}}\n",
        "\n",
        "data: [DONE]\n",
        "\n",
    );
    let (upstream, captured) =
        spawn_mock_upstream(StatusCode::OK, "text/event-stream", sse_body).await;
    let (proxy, db) = spawn_proxy(&upstream).await;

    let resp = reqwest::Client::new()
        .post(format!("{}/groq/openai/v1/chat/completions", proxy))
        .json(&json!({"model": "llama-3.3-70b", "stream": true, "messages": []}))
        .send()
        .await
        .unwrap();
    assert_eq!(resp.status(), 200);
    resp.text().await.unwrap();

    // The proxy must have injected stream_options so the upstream emits the
    // usage block at all
    let seen = captured.lock().unwrap().first().cloned().unwrap();
    assert_eq!(seen.body["stream_options"]["include_usage"], json!(true));

    let row = wait_for_request_row(&db).await;
    assert_eq!(row.provider, "groq");
    assert_eq!(row.model, "llama-3.3-70b");
    assert_eq!(row.input_tokens, 60);
    assert_eq!(row.output_tokens, 40);
    assert_eq!(row.cached_tokens, 20);
    assert!(row.is_streaming);
}

#[tokio::test]
async fn upstream_error_passes_through_and_is_recorded() {
    let (upstream, _captured) = spawn_mock_upstream(
        StatusCode::INTERNAL_SERVER_ERROR,
        "application/json",
        r#"{"error": {"message": "upstream exploded"}}"#,
    )
    .await;
    let (proxy, db) = spawn_proxy(&upstream).await;

    let resp = reqwest::Client::new()
        .post(format!("{}/anthropic/v1/messages", proxy))
        .json(&json!({"model": "claude-sonnet-4-6", "messages": []}))
        .send()
        .await
        .unwrap();
    assert_eq!(resp.status(), 500);

    let row = wait_for_request_row(&db).await;
    assert!(!row.is_complete);
    assert_eq!(row.input_tokens, 0);
    let err = row.error_message.expect("error_message should be set");
    assert!(err.contains("HTTP 500"), "got: {}", err);
}

#[tokio::test]
async fn budget_crud_lifecycle_through_the_api() {
    let (upstream, _captured) =
        spawn_mock_upstream(StatusCode::OK, "application/json", "{}").await;
    let (proxy, _db) = spawn_proxy(&upstream).await;
    let client = reqwest::Client::new();

    // Create
    let created: Value = client
        .post(format!("{}/api/budgets", proxy))
        .json(&json!({"name": "Monthly cap", "period": "monthly", "threshold_usd": 50.0}))
        .send()
        .await
        .unwrap()
        .json()
        .await
        .unwrap();
    assert_eq!(created["status"], "ok");
    let id = created["id"].as_i64().expect("created budget id");

    // Invalid create is rejected with 400, not silently accepted
    let bad = client
        .post(format!("{}/api/budgets", proxy))
        .json(&json!({"name": "broken", "period": "monthly", "threshold_usd": -5}))
        .send()
        .await
        .unwrap();
    assert_eq!(bad.status(), 400);

    // List shows it with live status fields
    let listed: Value = client
        .get(format!("{}/api/budgets", proxy))
        .send()
        .await
        .unwrap()
        .json()
        .await
        .unwrap();
    let budgets = listed["budgets"].as_array().unwrap();
    assert_eq!(budgets.len(), 1);
    assert_eq!(budgets[0]["name"], "Monthly cap");
    assert_eq!(budgets[0]["threshold_usd"], json!(50.0));
    assert_eq!(budgets[0]["enabled"], json!(true));

    // Full update
    let updated: Value = client
        .put(format!("{}/api/budgets/{}", proxy, id))
        .json(&json!({
            "name": "Monthly cap v2", "period": "monthly", "threshold_usd": 75.0,
            "provider_filter": "anthropic", "enabled": true
        }))
        .send()
        .await
        .unwrap()
        .json()
        .await
        .unwrap();
    assert_eq!(updated["status"], "ok");

    // Toggle off
    let toggled: Value = client
        .put(format!("{}/api/budgets/{}/enabled", proxy, id))
        .json(&json!({"enabled": false}))
        .send()
        .await
        .unwrap()
        .json()
        .await
        .unwrap();
    assert_eq!(toggled["status"], "ok");

    let listed: Value = client
        .get(format!("{}/api/budgets", proxy))
        .send()
        .await
        .unwrap()
        .json()
        .await
        .unwrap();
    let b = &listed["budgets"][0];
    assert_eq!(b["name"], "Monthly cap v2");
    assert_eq!(b["threshold_usd"], json!(75.0));
    assert_eq!(b["provider_filter"], "anthropic");
    assert_eq!(b["enabled"], json!(false));

    // Delete, then the list is empty
    let deleted: Value = client
        .delete(format!("{}/api/budgets/{}", proxy, id))
        .send()
        .await
        .unwrap()
        .json()
        .await
        .unwrap();
    assert_eq!(deleted["status"], "ok");
    let listed: Value = client
        .get(format!("{}/api/budgets", proxy))
        .send()
        .await
        .unwrap()
        .json()
        .await
        .unwrap();
    assert_eq!(listed["budgets"].as_array().unwrap().len(), 0);
}

#[tokio::test]
async fn health_endpoint_reports_ok_and_request_count() {
    let (upstream, _captured) =
        spawn_mock_upstream(StatusCode::OK, "application/json", "{}").await;
    let (proxy, _db) = spawn_proxy(&upstream).await;

    let body: Value = reqwest::get(format!("{}/health", proxy))
        .await
        .unwrap()
        .json()
        .await
        .unwrap();
    assert_eq!(body["status"], "ok");
    assert_eq!(body["service"], "tokenpulse-proxy");
    assert_eq!(body["total_requests_tracked"], json!(0));
}
