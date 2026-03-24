use axum::{
    Router,
    extract::{Request, State},
    response::Response,
    routing::any,
    body::Body,
};
use bytes::Bytes;
use chrono::Utc;
use futures::StreamExt;
use http::{HeaderMap, Method, StatusCode};
use reqwest::Client;
use serde_json::Value;
use std::sync::{Arc, Mutex};
use std::sync::atomic::{AtomicBool, Ordering};
use tower_http::cors::{Any, CorsLayer};

use crate::db::{insert_request, RequestRecord};
use crate::pricing::calculate_cost_with_db;

#[derive(Clone)]
pub struct AppState {
    pub db: Arc<Mutex<rusqlite::Connection>>,
    pub http_client: Client,
    pub proxy_paused: Arc<AtomicBool>,
}

#[derive(Debug, Clone)]
pub struct ProviderInfo {
    pub name: String,
    pub base_url: String,
}

fn detect_provider(headers: &HeaderMap, path: &str) -> ProviderInfo {
    // Check path-based routing first
    if path.starts_with("/anthropic/") {
        return ProviderInfo {
            name: "anthropic".to_string(),
            base_url: "https://api.anthropic.com".to_string(),
        };
    }
    if path.starts_with("/google/") {
        return ProviderInfo {
            name: "google".to_string(),
            base_url: "https://generativelanguage.googleapis.com".to_string(),
        };
    }
    if path.starts_with("/ollama/") || path.contains("ollama") {
        return ProviderInfo {
            name: "ollama".to_string(),
            base_url: "http://localhost:11434".to_string(),
        };
    }
    if path.starts_with("/lmstudio/") {
        return ProviderInfo {
            name: "lmstudio".to_string(),
            base_url: "http://localhost:1234".to_string(),
        };
    }
    if path.starts_with("/mistral/") {
        return ProviderInfo {
            name: "mistral".to_string(),
            base_url: "https://api.mistral.ai".to_string(),
        };
    }
    if path.starts_with("/groq/") {
        return ProviderInfo {
            name: "groq".to_string(),
            base_url: "https://api.groq.com".to_string(),
        };
    }
    if path.starts_with("/cliproxy/") {
        return ProviderInfo {
            name: "cliproxy".to_string(),
            base_url: "http://127.0.0.1:8317".to_string(),
        };
    }

    // Check auth header
    if let Some(auth) = headers.get("authorization") {
        if let Ok(auth_str) = auth.to_str() {
            let token = auth_str.trim_start_matches("Bearer ").trim_start_matches("bearer ");
            if token.starts_with("sk-ant-") {
                return ProviderInfo {
                    name: "anthropic".to_string(),
                    base_url: "https://api.anthropic.com".to_string(),
                };
            }
            if token.starts_with("AIza") {
                return ProviderInfo {
                    name: "google".to_string(),
                    base_url: "https://generativelanguage.googleapis.com".to_string(),
                };
            }
        }
    }

    // Check x-api-key header (Anthropic style)
    if let Some(api_key) = headers.get("x-api-key") {
        if let Ok(key_str) = api_key.to_str() {
            if key_str.starts_with("sk-ant-") {
                return ProviderInfo {
                    name: "anthropic".to_string(),
                    base_url: "https://api.anthropic.com".to_string(),
                };
            }
        }
    }

    // Check host header for local models
    if let Some(host) = headers.get("host") {
        if let Ok(host_str) = host.to_str() {
            if host_str.contains("11434") || host_str.contains("ollama") {
                return ProviderInfo {
                    name: "ollama".to_string(),
                    base_url: "http://localhost:11434".to_string(),
                };
            }
            if host_str.contains("1234") {
                return ProviderInfo {
                    name: "lmstudio".to_string(),
                    base_url: "http://localhost:1234".to_string(),
                };
            }
        }
    }

    // Default to OpenAI
    ProviderInfo {
        name: "openai".to_string(),
        base_url: "https://api.openai.com".to_string(),
    }
}

fn extract_model(body: &Value, provider: &str) -> String {
    match provider {
        "google" => {
            body.get("model")
                .and_then(|v| v.as_str())
                .unwrap_or("gemini-unknown")
                .to_string()
        }
        _ => body
            .get("model")
            .and_then(|v| v.as_str())
            .unwrap_or("unknown")
            .to_string(),
    }
}

fn extract_usage(body: &Value, provider: &str) -> (i64, i64, i64, i64) {
    // Returns (input_tokens, output_tokens, cached_tokens, reasoning_tokens)
    match provider {
        "anthropic" => {
            let usage = body.get("usage").unwrap_or(&Value::Null);
            let input = usage.get("input_tokens").and_then(|v| v.as_i64()).unwrap_or(0);
            let output = usage.get("output_tokens").and_then(|v| v.as_i64()).unwrap_or(0);
            let cached = usage.get("cache_read_input_tokens").and_then(|v| v.as_i64()).unwrap_or(0);
            (input, output, cached, 0)
        }
        "google" => {
            let usage = body.get("usageMetadata").unwrap_or(&Value::Null);
            let input = usage.get("promptTokenCount").and_then(|v| v.as_i64()).unwrap_or(0);
            let output = usage.get("candidatesTokenCount").and_then(|v| v.as_i64()).unwrap_or(0);
            (input, output, 0, 0)
        }
        "ollama" => {
            let input = body.get("prompt_eval_count").and_then(|v| v.as_i64()).unwrap_or(0);
            let output = body.get("eval_count").and_then(|v| v.as_i64()).unwrap_or(0);
            (input, output, 0, 0)
        }
        _ => {
            // OpenAI and OpenAI-compatible
            let usage = body.get("usage").unwrap_or(&Value::Null);
            let input = usage.get("prompt_tokens").and_then(|v| v.as_i64()).unwrap_or(0);
            let output = usage.get("completion_tokens").and_then(|v| v.as_i64()).unwrap_or(0);
            let cached = usage.get("prompt_tokens_details")
                .and_then(|d| d.get("cached_tokens"))
                .and_then(|v| v.as_i64())
                .unwrap_or(0);
            let reasoning = usage.get("completion_tokens_details")
                .and_then(|d| d.get("reasoning_tokens"))
                .and_then(|v| v.as_i64())
                .unwrap_or(0);
            (input, output, cached, reasoning)
        }
    }
}

fn is_streaming_request(body: &Value) -> bool {
    body.get("stream")
        .and_then(|v| v.as_bool())
        .unwrap_or(false)
}

fn build_forward_path(provider: &ProviderInfo, original_path: &str) -> String {
    let stripped = match provider.name.as_str() {
        "anthropic" => original_path.strip_prefix("/anthropic").unwrap_or(original_path),
        "google" => original_path.strip_prefix("/google").unwrap_or(original_path),
        "ollama" => original_path.strip_prefix("/ollama").unwrap_or(original_path),
        "lmstudio" => original_path.strip_prefix("/lmstudio").unwrap_or(original_path),
        "mistral" => original_path.strip_prefix("/mistral").unwrap_or(original_path),
        "groq" => original_path.strip_prefix("/groq").unwrap_or(original_path),
        "cliproxy" => original_path.strip_prefix("/cliproxy").unwrap_or(original_path),
        _ => original_path,
    };
    stripped.to_string()
}

async fn proxy_handler(
    State(state): State<AppState>,
    req: Request<Body>,
) -> Result<Response<Body>, StatusCode> {
    // Return 503 if proxy is paused
    if state.proxy_paused.load(Ordering::SeqCst) {
        return Err(StatusCode::SERVICE_UNAVAILABLE);
    }

    let start_time = std::time::Instant::now();
    let start_timestamp = Utc::now().to_rfc3339();

    let (parts, body) = req.into_parts();
    let path = parts.uri.path().to_string();
    let query = parts.uri.query().map(|q| format!("?{}", q)).unwrap_or_default();

    let provider = detect_provider(&parts.headers, &path);
    let forward_path = build_forward_path(&provider, &path);
    let target_url = format!("{}{}{}", provider.base_url, forward_path, query);

    // Read request body
    let body_bytes = match axum::body::to_bytes(body, 10 * 1024 * 1024).await {
        Ok(b) => b,
        Err(_) => return Err(StatusCode::BAD_REQUEST),
    };

    let body_json_result: Result<Value, _> = serde_json::from_slice(&body_bytes);
    let mut body_json = body_json_result.unwrap_or(Value::Null);
    let has_json_body = body_json != Value::Null;
    let model = extract_model(&body_json, &provider.name);
    let is_streaming = is_streaming_request(&body_json);

    eprintln!("[TokenPulse] {} {} → {} (provider: {}, model: {}, streaming: {})",
        parts.method, path, target_url, provider.name, model, is_streaming);

    // Inject stream_options for OpenAI streaming requests
    if is_streaming && (provider.name == "openai" || provider.name == "cliproxy") {
        if let Some(obj) = body_json.as_object_mut() {
            obj.insert(
                "stream_options".to_string(),
                serde_json::json!({"include_usage": true}),
            );
        }
    }

    // Use original bytes if body wasn't valid JSON (e.g. GET requests)
    let modified_body = if has_json_body {
        serde_json::to_vec(&body_json).unwrap_or_else(|_| body_bytes.to_vec())
    } else {
        body_bytes.to_vec()
    };

    // Build forward request — pass ALL original headers through
    let mut forward_headers = reqwest::header::HeaderMap::new();
    for (name, value) in &parts.headers {
        let name_str = name.as_str();
        // Skip only hop-by-hop headers and host (host gets set by reqwest for the target URL)
        if matches!(name_str, "host" | "connection" | "transfer-encoding" | "content-length") {
            continue;
        }
        if let Ok(val) = reqwest::header::HeaderValue::from_bytes(value.as_bytes()) {
            if let Ok(header_name) = reqwest::header::HeaderName::from_bytes(name.as_str().as_bytes()) {
                forward_headers.insert(header_name, val);
            }
        }
    }
    eprintln!("[TokenPulse] Forwarding {} headers (auth present: {})",
        forward_headers.len(),
        forward_headers.contains_key("authorization") || forward_headers.contains_key("x-api-key"));

    let method = match parts.method {
        Method::GET => reqwest::Method::GET,
        Method::POST => reqwest::Method::POST,
        Method::PUT => reqwest::Method::PUT,
        Method::DELETE => reqwest::Method::DELETE,
        Method::PATCH => reqwest::Method::PATCH,
        _ => reqwest::Method::POST,
    };

    let forward_req = state.http_client
        .request(method, &target_url)
        .headers(forward_headers)
        .body(modified_body)
        .build()
        .map_err(|e| {
            eprintln!("[TokenPulse] ERROR building request: {}", e);
            StatusCode::INTERNAL_SERVER_ERROR
        })?;

    let response = match state.http_client.execute(forward_req).await {
        Ok(r) => {
            eprintln!("[TokenPulse] Response: {} from {}", r.status(), target_url);
            r
        },
        Err(e) => {
            eprintln!("[TokenPulse] ERROR forwarding to {}: {}", target_url, e);
            // Log the failed attempt
            let latency_ms = start_time.elapsed().as_millis() as i64;
            let record = RequestRecord {
                id: None,
                timestamp: start_timestamp,
                provider: provider.name.clone(),
                model: model.clone(),
                input_tokens: 0,
                output_tokens: 0,
                cached_tokens: 0,
                reasoning_tokens: 0,
                cost_usd: 0.0,
                latency_ms,
                tokens_per_second: 0.0,
                time_to_first_token_ms: -1,
                is_streaming,
                is_complete: false,
                source_tag: String::new(),
                error_message: Some(e.to_string()),
            };
            if let Ok(conn) = state.db.lock() {
                let _ = insert_request(&conn, &record);
            }
            return Err(StatusCode::BAD_GATEWAY);
        }
    };

    let status = response.status();
    let resp_headers = response.headers().clone();

    // Log error responses from the upstream provider
    if !status.is_success() && !is_streaming {
        let resp_bytes = response.bytes().await.map_err(|_| StatusCode::BAD_GATEWAY)?;
        let latency_ms = start_time.elapsed().as_millis() as i64;
        let error_text = String::from_utf8_lossy(&resp_bytes).to_string();
        let record = RequestRecord {
            id: None,
            timestamp: start_timestamp,
            provider: provider.name.clone(),
            model: model.clone(),
            input_tokens: 0,
            output_tokens: 0,
            cached_tokens: 0,
            reasoning_tokens: 0,
            cost_usd: 0.0,
            latency_ms,
            tokens_per_second: 0.0,
            time_to_first_token_ms: -1,
            is_streaming: false,
            is_complete: false,
            source_tag: String::new(),
            error_message: Some(format!("HTTP {}: {}", status.as_u16(), &error_text[..error_text.len().min(200)])),
        };
        if let Ok(conn) = state.db.lock() {
            let _ = insert_request(&conn, &record);
        }
        let mut response_builder = Response::builder().status(status.as_u16());
        for (name, value) in &resp_headers {
            if let Ok(header_name) = http::header::HeaderName::from_bytes(name.as_str().as_bytes()) {
                response_builder = response_builder.header(header_name, value.as_bytes());
            }
        }
        return Ok(response_builder.body(Body::from(resp_bytes)).unwrap());
    }

    if is_streaming {
        // Stream response back, collecting chunks to find usage
        let mut stream = response.bytes_stream();
        let (tx, rx) = tokio::sync::mpsc::channel::<Result<Bytes, std::io::Error>>(100);
        let provider_name = provider.name.clone();
        let db = state.db.clone();
        let model_clone = model.clone();

        tokio::spawn(async move {
            let mut last_chunk_json: Option<Value> = None;
            let mut ttft_ms: i64 = -1;
            let mut first_chunk = true;

            while let Some(chunk_result) = stream.next().await {
                match chunk_result {
                    Ok(chunk) => {
                        if first_chunk {
                            ttft_ms = start_time.elapsed().as_millis() as i64;
                            first_chunk = false;
                        }

                        // Try to parse SSE data lines for usage
                        if let Ok(text) = std::str::from_utf8(&chunk) {
                            for line in text.lines() {
                                if let Some(data) = line.strip_prefix("data: ") {
                                    if data.trim() != "[DONE]" {
                                        if let Ok(json) = serde_json::from_str::<Value>(data) {
                                            last_chunk_json = Some(json);
                                        }
                                    }
                                }
                            }
                        }

                        let _ = tx.send(Ok(chunk)).await;
                    }
                    Err(e) => {
                        let _ = tx.send(Err(std::io::Error::new(std::io::ErrorKind::Other, e.to_string()))).await;
                        break;
                    }
                }
            }

            // Extract usage from last chunk
            if let Some(json) = last_chunk_json {
                let (input_tokens, output_tokens, cached_tokens, reasoning_tokens) =
                    extract_usage(&json, &provider_name);
                let latency_ms = start_time.elapsed().as_millis() as i64;
                let cost = if let Ok(conn) = db.lock() {
                    calculate_cost_with_db(&conn, &model_clone, input_tokens as u32, output_tokens as u32)
                } else {
                    0.0
                };
                let tps = if latency_ms > 0 {
                    (output_tokens as f64) / (latency_ms as f64 / 1000.0)
                } else {
                    0.0
                };

                let record = RequestRecord {
                    id: None,
                    timestamp: start_timestamp,
                    provider: provider_name,
                    model: model_clone,
                    input_tokens,
                    output_tokens,
                    cached_tokens,
                    reasoning_tokens,
                    cost_usd: cost,
                    latency_ms,
                    tokens_per_second: tps,
                    time_to_first_token_ms: ttft_ms,
                    is_streaming: true,
                    is_complete: true,
                    source_tag: String::new(),
                    error_message: None,
                };

                if let Ok(conn) = db.lock() {
                    let _ = insert_request(&conn, &record);
                }
            }
        });

        let stream_body = Body::from_stream(
            tokio_stream::wrappers::ReceiverStream::new(rx)
        );

        let mut response_builder = Response::builder().status(status.as_u16());
        for (name, value) in &resp_headers {
            if let Ok(header_name) = http::header::HeaderName::from_bytes(name.as_str().as_bytes()) {
                response_builder = response_builder.header(header_name, value.as_bytes());
            }
        }

        Ok(response_builder.body(stream_body).unwrap())
    } else {
        // Non-streaming: read full response
        let resp_bytes = response.bytes().await.map_err(|_| StatusCode::BAD_GATEWAY)?;
        let latency_ms = start_time.elapsed().as_millis() as i64;

        if let Ok(json) = serde_json::from_slice::<Value>(&resp_bytes) {
            let (input_tokens, output_tokens, cached_tokens, reasoning_tokens) =
                extract_usage(&json, &provider.name);
            let cost = if let Ok(conn) = state.db.lock() {
                calculate_cost_with_db(&conn, &model, input_tokens as u32, output_tokens as u32)
            } else {
                0.0
            };
            let tps = if latency_ms > 0 {
                (output_tokens as f64) / (latency_ms as f64 / 1000.0)
            } else {
                0.0
            };

            let record = RequestRecord {
                id: None,
                timestamp: start_timestamp,
                provider: provider.name.clone(),
                model: model.clone(),
                input_tokens,
                output_tokens,
                cached_tokens,
                reasoning_tokens,
                cost_usd: cost,
                latency_ms,
                tokens_per_second: tps,
                time_to_first_token_ms: -1,
                is_streaming: false,
                is_complete: true,
                source_tag: String::new(),
                error_message: None,
            };

            if let Ok(conn) = state.db.lock() {
                let _ = insert_request(&conn, &record);
            }
        }

        let mut response_builder = Response::builder().status(status.as_u16());
        for (name, value) in &resp_headers {
            let name_str = name.as_str();
            if matches!(name_str, "transfer-encoding" | "connection") {
                continue;
            }
            if let Ok(header_name) = http::header::HeaderName::from_bytes(name_str.as_bytes()) {
                response_builder = response_builder.header(header_name, value.as_bytes());
            }
        }

        Ok(response_builder
            .body(Body::from(resp_bytes))
            .unwrap())
    }
}

pub async fn start_proxy_server(
    db: Arc<Mutex<rusqlite::Connection>>,
    proxy_running: Arc<AtomicBool>,
    proxy_paused: Arc<AtomicBool>,
) {
    let http_client = Client::builder()
        .timeout(std::time::Duration::from_secs(300))
        .build()
        .expect("Failed to build HTTP client");

    let state = AppState { db, http_client, proxy_paused };

    let cors = CorsLayer::new()
        .allow_origin(Any)
        .allow_methods(Any)
        .allow_headers(Any);

    let app = Router::new()
        .fallback(any(proxy_handler))
        .layer(cors)
        .with_state(state);

    match tokio::net::TcpListener::bind("0.0.0.0:4100").await {
        Ok(listener) => {
            proxy_running.store(true, Ordering::SeqCst);
            eprintln!("TokenPulse proxy listening on port 4100");
            axum::serve(listener, app).await.ok();
            proxy_running.store(false, Ordering::SeqCst);
        }
        Err(e) => {
            eprintln!("Failed to bind proxy port 4100: {}. Is another instance running?", e);
            proxy_running.store(false, Ordering::SeqCst);
        }
    }
}
