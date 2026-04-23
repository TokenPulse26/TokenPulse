use axum::{
    body::Body,
    extract::{Request, State},
    response::Response,
    routing::any,
    Router,
};
use bytes::Bytes;
use chrono::Utc;
use futures::StreamExt;
use http::{header, HeaderMap, Method, StatusCode};
use once_cell::sync::Lazy;
use reqwest::Client;
use serde_json::Value;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use tower_http::cors::{AllowOrigin, CorsLayer};

use crate::db::{self, insert_request, RequestRecord};
use crate::pricing::calculate_cost_with_db;

/// Process start time for uptime calculation.
static PROCESS_START: Lazy<std::time::Instant> = Lazy::new(std::time::Instant::now);

/// Query-string keys that carry provider credentials. Any occurrence is
/// replaced with a fixed "REDACTED" marker before logging a URL or storing
/// an upstream error body.
const SECRET_QUERY_KEYS: &[&str] = &["key", "api_key", "access_token", "token"];

/// Rewrite a URL so sensitive query parameters are replaced with "REDACTED".
/// Used before any URL gets written to stderr. Returns the original string on
/// parse failure rather than dropping it, because the logs are diagnostic.
fn redact_url_secrets(url_str: &str) -> String {
    match url::Url::parse(url_str) {
        Ok(mut u) => {
            let pairs: Vec<(String, String)> = u
                .query_pairs()
                .map(|(k, v)| {
                    let k = k.into_owned();
                    let v = if SECRET_QUERY_KEYS.iter().any(|s| k.eq_ignore_ascii_case(s)) {
                        "REDACTED".to_string()
                    } else {
                        v.into_owned()
                    };
                    (k, v)
                })
                .collect();
            if pairs.is_empty() {
                u.set_query(None);
            } else {
                let mut ser = u.query_pairs_mut();
                ser.clear();
                for (k, v) in &pairs {
                    ser.append_pair(k, v);
                }
                drop(ser);
            }
            u.to_string()
        }
        Err(_) => url_str.to_string(),
    }
}

/// Replace anything that looks like an AI provider API key inside a free-form
/// string (e.g. an upstream error body) with "REDACTED". Covers the common
/// prefixes we already recognize in `detect_provider`, plus a generic
/// "Bearer <token>" pattern. Used before persisting upstream error responses.
fn redact_secrets_in_text(text: &str) -> String {
    let mut out = String::with_capacity(text.len());
    let mut rest = text;
    let prefixes = ["sk-ant-", "sk-proj-", "sk-", "AIza", "gsk_"];
    'outer: while !rest.is_empty() {
        for prefix in &prefixes {
            if let Some(pos) = rest.find(prefix) {
                out.push_str(&rest[..pos]);
                out.push_str("REDACTED");
                // Skip the token: consume prefix + following non-whitespace/non-quote chars.
                let tail = &rest[pos + prefix.len()..];
                let end = tail
                    .find(|c: char| {
                        c.is_whitespace() || matches!(c, '"' | '\'' | ',' | '}' | ')' | ']')
                    })
                    .unwrap_or(tail.len());
                rest = &tail[end..];
                continue 'outer;
            }
        }
        // No more known prefixes. Also scrub "Bearer <token>" sequences.
        if let Some(pos) = rest.find("Bearer ") {
            out.push_str(&rest[..pos + "Bearer ".len()]);
            let tail = &rest[pos + "Bearer ".len()..];
            let end = tail
                .find(|c: char| {
                    c.is_whitespace() || matches!(c, '"' | '\'' | ',' | '}' | ')' | ']')
                })
                .unwrap_or(tail.len());
            out.push_str("REDACTED");
            rest = &tail[end..];
            continue;
        }
        out.push_str(rest);
        break;
    }
    out
}

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
    if path.starts_with("/openrouter/") {
        return ProviderInfo {
            name: "openrouter".to_string(),
            base_url: "https://openrouter.ai".to_string(),
        };
    }
    if path.starts_with("/openai-codex/") {
        return ProviderInfo {
            name: "openai-codex".to_string(),
            base_url: "https://chatgpt.com/backend-api".to_string(),
        };
    }

    // Check auth header
    if let Some(auth) = headers.get("authorization") {
        if let Ok(auth_str) = auth.to_str() {
            let token = auth_str
                .trim_start_matches("Bearer ")
                .trim_start_matches("bearer ");
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

fn extract_model(body: &Value, provider: &str, path: &str) -> String {
    fn candidate_from_path(path: &str) -> Option<String> {
        if let Some(idx) = path.find("/models/") {
            let after = &path[idx + "/models/".len()..];
            let model_name = after
                .split([':', '/', '?'])
                .next()
                .unwrap_or("")
                .trim()
                .to_string();
            if !model_name.is_empty() {
                return Some(model_name);
            }
        }
        if let Some(idx) = path.find("/engines/") {
            let after = &path[idx + "/engines/".len()..];
            let model_name = after
                .split(['/', '?'])
                .next()
                .unwrap_or("")
                .trim()
                .to_string();
            if !model_name.is_empty() {
                return Some(model_name);
            }
        }
        None
    }

    fn candidate_from_body(body: &Value) -> Option<String> {
        let candidates = [
            body.get("model").and_then(|v| v.as_str()),
            body.get("model_name").and_then(|v| v.as_str()),
            body.get("deployment").and_then(|v| v.as_str()),
            body.get("engine").and_then(|v| v.as_str()),
            body.get("metadata")
                .and_then(|v| v.get("model"))
                .and_then(|v| v.as_str()),
        ];
        candidates
            .into_iter()
            .flatten()
            .map(str::trim)
            .find(|value| !value.is_empty())
            .map(str::to_string)
    }

    match provider {
        "google" => {
            // Try body first
            if let Some(m) = candidate_from_body(body) {
                return m.to_string();
            }
            // Google puts model in URL: /v1beta/models/gemini-1.5-pro:generateContent
            if let Some(model_name) = candidate_from_path(path) {
                return model_name;
            }
            "gemini-unknown".to_string()
        }
        _ => candidate_from_body(body)
            .or_else(|| candidate_from_path(path))
            .unwrap_or_else(|| "unknown".to_string()),
    }
}

fn extract_usage(body: &Value, provider: &str) -> (i64, i64, i64, i64) {
    // Returns (input_tokens, output_tokens, cached_tokens, reasoning_tokens)
    match provider {
        "anthropic" => {
            let usage = body.get("usage").unwrap_or(&Value::Null);
            let input = usage
                .get("input_tokens")
                .and_then(|v| v.as_i64())
                .unwrap_or(0);
            let output = usage
                .get("output_tokens")
                .and_then(|v| v.as_i64())
                .unwrap_or(0);
            let cached = usage
                .get("cache_read_input_tokens")
                .and_then(|v| v.as_i64())
                .unwrap_or(0);
            (input, output, cached, 0)
        }
        "google" => {
            let usage = body.get("usageMetadata").unwrap_or(&Value::Null);
            let input = usage
                .get("promptTokenCount")
                .and_then(|v| v.as_i64())
                .unwrap_or(0);
            let output = usage
                .get("candidatesTokenCount")
                .and_then(|v| v.as_i64())
                .unwrap_or(0);
            (input, output, 0, 0)
        }
        "ollama" | "lmstudio" => {
            // Try Ollama native format first (prompt_eval_count / eval_count)
            let native_input = body
                .get("prompt_eval_count")
                .and_then(|v| v.as_i64())
                .unwrap_or(0);
            let native_output = body.get("eval_count").and_then(|v| v.as_i64()).unwrap_or(0);
            if native_input > 0 || native_output > 0 {
                return (native_input, native_output, 0, 0);
            }
            // Fall through to OpenAI-compatible format (usage.prompt_tokens)
            let usage = body.get("usage").unwrap_or(&Value::Null);
            let input = usage
                .get("prompt_tokens")
                .and_then(|v| v.as_i64())
                .unwrap_or(0);
            let output = usage
                .get("completion_tokens")
                .and_then(|v| v.as_i64())
                .unwrap_or(0);
            (input, output, 0, 0)
        }
        _ => {
            // OpenAI and OpenAI-compatible
            let usage = body.get("usage").unwrap_or(&Value::Null);
            let input = usage
                .get("prompt_tokens")
                .and_then(|v| v.as_i64())
                .unwrap_or(0);
            let output = usage
                .get("completion_tokens")
                .and_then(|v| v.as_i64())
                .unwrap_or(0);
            let cached = usage
                .get("prompt_tokens_details")
                .and_then(|d| d.get("cached_tokens"))
                .and_then(|v| v.as_i64())
                .unwrap_or(0);
            let reasoning = usage
                .get("completion_tokens_details")
                .and_then(|d| d.get("reasoning_tokens"))
                .and_then(|v| v.as_i64())
                .unwrap_or(0);
            (input, output, cached, reasoning)
        }
    }
}

fn get_provider_type(provider: &str) -> String {
    match provider {
        "cliproxy" => "subscription".to_string(),
        "ollama" | "lmstudio" => "local".to_string(),
        _ => "api".to_string(),
    }
}

fn is_streaming_request(body: &Value) -> bool {
    body.get("stream")
        .and_then(|v| v.as_bool())
        .unwrap_or(false)
}

/// Detect whether a request path targets an OpenAI-style **Responses API**
/// (as opposed to Chat Completions). Responses API endpoints accept a
/// completely different request shape and reject `stream_options`.
///
/// Examples that should return `true`:
///   - `/openai-codex/codex/responses`  (ChatGPT Plus Codex OAuth backend)
///   - `/openai/v1/responses`           (OpenAI standard Responses API)
///   - `/azure-openai/.../responses`    (Azure OpenAI Responses)
///
/// Examples that should return `false`:
///   - `/openai/v1/chat/completions`
///   - `/cliproxy/v1/chat/completions`
///   - `/anthropic/v1/messages`
fn is_responses_api_path(path: &str) -> bool {
    // Match `responses` only as a full path segment, so `/v1/responses` and
    // `/codex/responses/<id>` are caught but `/v1/my-responses-list` is not.
    path.split('/').any(|seg| seg == "responses")
}

/// Extract usage from a single SSE event JSON object emitted by an OpenAI
/// Responses API stream. The Responses API ships token counts in the
/// terminal `response.completed` event under `response.usage` with field
/// names `input_tokens` / `output_tokens` (not `prompt_tokens` /
/// `completion_tokens` like Chat Completions).
///
/// Returns `(input, output, cached, reasoning)` if usage was found in this
/// event, otherwise `None`.
fn extract_responses_api_usage(event: &Value) -> Option<(i64, i64, i64, i64)> {
    // The usage block lives at event.response.usage. Some intermediate events
    // (response.created, response.in_progress) include `response.usage = null`,
    // so we only return Some when we actually find numeric tokens.
    let usage = event.get("response").and_then(|r| r.get("usage"))?;
    if usage.is_null() {
        return None;
    }
    let input = usage
        .get("input_tokens")
        .and_then(|v| v.as_i64())
        .unwrap_or(0);
    let output = usage
        .get("output_tokens")
        .and_then(|v| v.as_i64())
        .unwrap_or(0);
    let cached = usage
        .get("input_tokens_details")
        .and_then(|d| d.get("cached_tokens"))
        .and_then(|v| v.as_i64())
        .unwrap_or(0);
    let reasoning = usage
        .get("output_tokens_details")
        .and_then(|d| d.get("reasoning_tokens"))
        .and_then(|v| v.as_i64())
        .unwrap_or(0);
    if input == 0 && output == 0 {
        return None;
    }
    Some((input, output, cached, reasoning))
}

fn extract_sse_field_value<'a>(line: &'a str, field: &str) -> Option<&'a str> {
    let rest = line.strip_prefix(field)?;
    Some(rest.strip_prefix(' ').unwrap_or(rest))
}

fn handle_stream_sse_event(
    provider_name: &str,
    model: &str,
    is_responses_api_stream: bool,
    event_name: Option<&str>,
    data: &str,
    last_chunk_json: &mut Option<Value>,
    responses_api_usage: &mut Option<(i64, i64, i64, i64)>,
    anthropic_input: &mut i64,
    anthropic_output: &mut i64,
    anthropic_cached: &mut i64,
) {
    let data = data.trim();
    if data.is_empty() || data == "[DONE]" {
        return;
    }

    match serde_json::from_str::<Value>(data) {
        Ok(json) => {
            if is_responses_api_stream {
                if let Some(usage) = extract_responses_api_usage(&json) {
                    *responses_api_usage = Some(usage);
                }
            }

            if provider_name == "anthropic" {
                let event_type = json
                    .get("type")
                    .and_then(|v| v.as_str())
                    .or(event_name)
                    .unwrap_or("unknown");

                if let Some(usage) = json.get("message").and_then(|msg| msg.get("usage")) {
                    if let Some(v) = usage.get("input_tokens").and_then(|v| v.as_i64()) {
                        *anthropic_input = v;
                    }
                    if let Some(v) = usage
                        .get("cache_read_input_tokens")
                        .and_then(|v| v.as_i64())
                    {
                        *anthropic_cached = v;
                    }
                    if let Some(v) = usage.get("output_tokens").and_then(|v| v.as_i64()) {
                        *anthropic_output = v;
                    }
                }

                if let Some(usage) = json.get("usage") {
                    if let Some(v) = usage.get("input_tokens").and_then(|v| v.as_i64()) {
                        *anthropic_input = v;
                    }
                    if let Some(v) = usage
                        .get("cache_read_input_tokens")
                        .and_then(|v| v.as_i64())
                    {
                        *anthropic_cached = v;
                    }
                    if let Some(v) = usage.get("output_tokens").and_then(|v| v.as_i64()) {
                        *anthropic_output = v;
                    }
                }

                // Only log on the terminal message_stop event — logging every
                // message_delta floods stderr for long streaming responses.
                if event_type == "message_stop" {
                    eprintln!(
                        "[TokenPulse] anthropic stream done model={} input_tokens={} output_tokens={} cached_tokens={}",
                        model, *anthropic_input, *anthropic_output, *anthropic_cached
                    );
                }
            }

            *last_chunk_json = Some(json);
        }
        Err(err) => {
            if provider_name == "anthropic" {
                let preview: String = data.chars().take(240).collect();
                eprintln!(
                    "[TokenPulse] anthropic stream parse error event={} model={} err={} data={}",
                    event_name.unwrap_or("unknown"),
                    model,
                    err,
                    preview
                );
            }
        }
    }
}

fn build_forward_path(provider: &ProviderInfo, original_path: &str) -> String {
    let stripped = match provider.name.as_str() {
        "anthropic" => original_path
            .strip_prefix("/anthropic")
            .unwrap_or(original_path),
        "google" => original_path
            .strip_prefix("/google")
            .unwrap_or(original_path),
        "ollama" => original_path
            .strip_prefix("/ollama")
            .unwrap_or(original_path),
        "lmstudio" => original_path
            .strip_prefix("/lmstudio")
            .unwrap_or(original_path),
        "mistral" => original_path
            .strip_prefix("/mistral")
            .unwrap_or(original_path),
        "groq" => original_path.strip_prefix("/groq").unwrap_or(original_path),
        "cliproxy" => original_path
            .strip_prefix("/cliproxy")
            .unwrap_or(original_path),
        "openrouter" => original_path
            .strip_prefix("/openrouter")
            .unwrap_or(original_path),
        "openai-codex" => original_path
            .strip_prefix("/openai-codex")
            .unwrap_or(original_path),
        _ => original_path,
    };
    stripped.to_string()
}

fn is_allowed_browser_origin(origin: &str) -> bool {
    if origin == "null" {
        return false;
    }

    match url::Url::parse(origin) {
        Ok(url) => {
            let host = match url.host_str() {
                Some(host) => host,
                None => return false,
            };
            matches!(host, "localhost" | "127.0.0.1" | "[::1]" | "::1")
                && url.port_or_known_default() == Some(4200)
                && matches!(url.scheme(), "http" | "https")
        }
        Err(_) => false,
    }
}

fn build_cors_layer() -> CorsLayer {
    let allow_origin = AllowOrigin::predicate(|origin, _| {
        origin
            .to_str()
            .map(is_allowed_browser_origin)
            .unwrap_or(false)
    });

    CorsLayer::new()
        .allow_origin(allow_origin)
        .allow_methods([Method::GET, Method::POST, Method::DELETE, Method::OPTIONS])
        .allow_headers([
            header::ACCEPT,
            header::AUTHORIZATION,
            header::CONTENT_TYPE,
            header::HeaderName::from_static("x-api-key"),
            header::HeaderName::from_static("x-tokenpulse-project"),
            header::HeaderName::from_static("x-tokenpulse-tag"),
        ])
}

fn reject_disallowed_api_origin(headers: &HeaderMap, path: &str) -> Option<Response<Body>> {
    // Browser requests (identified by Origin header) are restricted to the
    // local dashboard origin for every endpoint, not only `/api/*`.
    let origin = headers.get(header::ORIGIN)?.to_str().ok()?;
    if is_allowed_browser_origin(origin) {
        return None;
    }

    Some(json_response(
        StatusCode::FORBIDDEN,
        serde_json::json!({
            "status": "error",
            "path": path,
            "message": "TokenPulse local API only accepts browser requests from the local dashboard origin.",
        }),
    ))
}

fn build_response(status: StatusCode, content_type: &str, body: Body) -> Response<Body> {
    let mut response = Response::new(body);
    *response.status_mut() = status;
    response.headers_mut().insert(
        header::CONTENT_TYPE,
        header::HeaderValue::from_str(content_type)
            .unwrap_or_else(|_| header::HeaderValue::from_static("application/octet-stream")),
    );
    response
}

fn json_response(status: StatusCode, value: Value) -> Response<Body> {
    match serde_json::to_vec(&value) {
        Ok(body) => build_response(status, "application/json", Body::from(body)),
        Err(err) => {
            eprintln!("[TokenPulse] failed to serialize JSON response: {}", err);
            build_response(
                StatusCode::INTERNAL_SERVER_ERROR,
                "application/json",
                Body::from(r#"{"status":"error","message":"internal server error"}"#),
            )
        }
    }
}

fn response_with_headers(
    status: StatusCode,
    source_headers: &HeaderMap,
    body: Body,
    drop_hop_by_hop: bool,
) -> Response<Body> {
    let mut response = Response::new(body);
    *response.status_mut() = status;
    for (name, value) in source_headers {
        let name_str = name.as_str();
        if drop_hop_by_hop && matches!(name_str, "transfer-encoding" | "connection") {
            continue;
        }
        response.headers_mut().append(name.clone(), value.clone());
    }
    response
}

fn detect_source_tag(headers: &HeaderMap) -> String {
    // Explicit project header takes priority
    for header_name in &["x-tokenpulse-project", "x-tokenpulse-tag"] {
        if let Some(val) = headers.get(*header_name) {
            if let Ok(s) = val.to_str() {
                let trimmed = s.trim();
                if !trimmed.is_empty() {
                    return trimmed.to_string();
                }
            }
        }
    }

    // User-Agent sniffing
    if let Some(ua) = headers.get("user-agent") {
        if let Ok(ua_str) = ua.to_str() {
            let ua_lower = ua_str.to_lowercase();
            if ua_lower.contains("cursor") {
                return "cursor".to_string();
            }
            if ua_lower.contains("vscode") || ua_lower.contains("copilot") {
                return "vscode".to_string();
            }
            if ua_lower.contains("openclaw") || ua_lower.contains("clawd") {
                return "openclaw".to_string();
            }
            if ua_lower.contains("openwebui") {
                return "open-webui".to_string();
            }
            if ua_lower.contains("python") {
                return "python-sdk".to_string();
            }
            if ua_lower.contains("node") || ua_lower.contains("axios") {
                return "node-sdk".to_string();
            }
        }
    }

    "".to_string()
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
    let query = parts
        .uri
        .query()
        .map(|q| format!("?{}", q))
        .unwrap_or_default();

    if let Some(response) = reject_disallowed_api_origin(&parts.headers, &path) {
        return Ok(response);
    }

    // ── Health check endpoint ─────────────────────────────────────────
    if (path == "/" || path == "/health" || path == "/api/health") && parts.method == Method::GET {
        let (count, db_path, db_size_bytes): (i64, String, u64) = if let Ok(conn) = state.db.lock() {
            let c = conn.query_row("SELECT COUNT(*) FROM requests", [], |row| row.get(0))
                .unwrap_or(0);
            // Retrieve the database file path via PRAGMA database_list
            let path: String = conn
                .query_row("PRAGMA database_list", [], |row| row.get::<_, String>(2))
                .unwrap_or_default();
            let size = if !path.is_empty() {
                std::fs::metadata(&path).map(|m| m.len()).unwrap_or(0)
            } else {
                0
            };
            (c, path, size)
        } else {
            (-1, String::new(), 0)
        };
        let uptime_secs = PROCESS_START.elapsed().as_secs();
        let body = serde_json::json!({
            "status": "ok",
            "service": "tokenpulse-proxy",
            "version": env!("CARGO_PKG_VERSION"),
            "port": 4100,
            "uptime_seconds": uptime_secs,
            "proxy_paused": state.proxy_paused.load(Ordering::SeqCst),
            "total_requests_tracked": count,
            "dashboard_url": "http://127.0.0.1:4200",
            "db_path": db_path,
            "db_size_bytes": db_size_bytes,
        });
        return Ok(json_response(StatusCode::OK, body));
    }

    // ── /api/stats endpoint ───────────────────────────────────────────
    if path == "/api/stats" && parts.method == Method::GET {
        let range = parts
            .uri
            .query()
            .and_then(|q| {
                url::form_urlencoded::parse(q.as_bytes())
                    .find(|(k, _)| k == "range")
                    .map(|(_, v)| v.to_string())
            })
            .unwrap_or_else(|| "all".to_string());
        let range_str = match range.as_str() {
            "today" | "7d" | "30d" | "all" => range.as_str(),
            _ => "all",
        };

        let result = if let Ok(conn) = state.db.lock() {
            let summary = db::get_summary_stats(&conn, range_str).ok();
            let cost_summary = db::get_cost_summary(&conn, range_str).ok();
            let models = db::get_model_breakdown_for_range(&conn, range_str).ok();

            // Project breakdown
            let time_cond = match range_str {
                "today" => "WHERE timestamp >= datetime('now', 'start of day')",
                "7d" => "WHERE timestamp >= datetime('now', '-7 days')",
                "30d" => "WHERE timestamp >= datetime('now', '-30 days')",
                _ => "",
            };
            let projects: Vec<serde_json::Value> = {
                let query = if time_cond.is_empty() {
                    "SELECT COALESCE(source_tag,'unknown') as tag, COUNT(*) as cnt, \
                     COALESCE(SUM(cost_usd),0) as cost \
                     FROM requests GROUP BY tag ORDER BY cost DESC"
                        .to_string()
                } else {
                    format!(
                        "SELECT COALESCE(source_tag,'unknown') as tag, COUNT(*) as cnt, \
                         COALESCE(SUM(cost_usd),0) as cost \
                         FROM requests {} GROUP BY tag ORDER BY cost DESC",
                        time_cond
                    )
                };
                let mut stmt = conn.prepare(&query).ok();
                if let Some(ref mut s) = stmt {
                    s.query_map([], |row| {
                        Ok(serde_json::json!({
                            "tag": row.get::<_, String>(0).unwrap_or_default(),
                            "requests": row.get::<_, i64>(1).unwrap_or(0),
                            "cost_usd": row.get::<_, f64>(2).unwrap_or(0.0),
                        }))
                    })
                    .ok()
                    .map(|rows| rows.filter_map(|r| r.ok()).collect())
                    .unwrap_or_default()
                } else {
                    Vec::new()
                }
            };

            let s = summary.unwrap_or(db::DashboardSummary {
                total_cost: 0.0,
                total_requests: 0,
                total_input_tokens: 0,
                total_output_tokens: 0,
            });
            let cs = cost_summary.unwrap_or(db::CostSummary {
                total_api_cost: 0.0,
                total_subscription_tokens: 0,
                total_local_tokens: 0,
            });

            let model_arr: Vec<serde_json::Value> = models
                .unwrap_or_default()
                .iter()
                .map(|m| {
                    let ptype = if m.provider == "cliproxy" {
                        "subscription"
                    } else if m.provider == "ollama" || m.provider == "lmstudio" {
                        "local"
                    } else {
                        "api"
                    };
                    serde_json::json!({
                        "model": m.model,
                        "provider": m.provider,
                        "requests": m.total_requests,
                        "tokens": m.total_tokens,
                        "cost_usd": m.total_cost,
                        "type": ptype,
                    })
                })
                .collect();

            serde_json::json!({
                "status": "ok",
                "range": range_str,
                "total_requests": s.total_requests,
                "total_input_tokens": s.total_input_tokens,
                "total_output_tokens": s.total_output_tokens,
                "api_cost_usd": cs.total_api_cost,
                "subscription_tokens": cs.total_subscription_tokens,
                "local_tokens": cs.total_local_tokens,
                "models": model_arr,
                "projects": projects,
            })
        } else {
            serde_json::json!({"status": "error", "message": "database lock failed"})
        };

        return Ok(json_response(StatusCode::OK, result));
    }

    // ── /api/requests endpoint ────────────────────────────────────────
    if path == "/api/requests" && parts.method == Method::GET {
        let params: std::collections::HashMap<String, String> = parts
            .uri
            .query()
            .map(|q| {
                url::form_urlencoded::parse(q.as_bytes())
                    .map(|(k, v)| (k.to_string(), v.to_string()))
                    .collect()
            })
            .unwrap_or_default();

        let limit: u32 = params
            .get("limit")
            .and_then(|v| v.parse().ok())
            .unwrap_or(50)
            .min(500);
        let range = params.get("range").map(|s| s.as_str()).unwrap_or("all");
        let range_str = match range {
            "today" | "7d" | "30d" | "all" => range,
            _ => "all",
        };

        let result = if let Ok(conn) = state.db.lock() {
            match db::get_requests_for_range(&conn, limit, range_str) {
                Ok(records) => serde_json::json!({
                    "status": "ok",
                    "range": range_str,
                    "limit": limit,
                    "count": records.len(),
                    "requests": records,
                }),
                Err(e) => serde_json::json!({"status": "error", "message": e.to_string()}),
            }
        } else {
            serde_json::json!({"status": "error", "message": "database lock failed"})
        };

        return Ok(json_response(StatusCode::OK, result));
    }

    // ── /api/reliability endpoint ─────────────────────────────────────
    if path == "/api/reliability" && parts.method == Method::GET {
        let range = parts
            .uri
            .query()
            .and_then(|q| {
                url::form_urlencoded::parse(q.as_bytes())
                    .find(|(k, _)| k == "range")
                    .map(|(_, v)| v.to_string())
            })
            .unwrap_or_else(|| "7d".to_string());
        let range_str = match range.as_str() {
            "today" | "7d" | "30d" | "all" => range.as_str(),
            _ => "7d",
        };

        let result = if let Ok(conn) = state.db.lock() {
            match db::get_reliability_snapshot(&conn, range_str) {
                Ok(snapshot) => serde_json::json!({
                    "status": "ok",
                    "reliability": snapshot,
                }),
                Err(e) => serde_json::json!({"status": "error", "message": e.to_string()}),
            }
        } else {
            serde_json::json!({"status": "error", "message": "database lock failed"})
        };

        return Ok(json_response(StatusCode::OK, result));
    }

    // ── /api/notifications endpoint ───────────────────────────────────
    if path == "/api/notifications" && parts.method == Method::GET {
        let limit = parts
            .uri
            .query()
            .and_then(|q| {
                url::form_urlencoded::parse(q.as_bytes())
                    .find(|(k, _)| k == "limit")
                    .and_then(|(_, v)| v.parse::<i64>().ok())
            })
            .unwrap_or(20);

        let result = if let Ok(conn) = state.db.lock() {
            match db::get_undelivered_notifications(&conn, limit) {
                Ok(items) => serde_json::json!({
                    "status": "ok",
                    "notifications": items,
                }),
                Err(e) => serde_json::json!({"status": "error", "message": e.to_string()}),
            }
        } else {
            serde_json::json!({"status": "error", "message": "database lock failed"})
        };

        return Ok(json_response(StatusCode::OK, result));
    }

    // ── /api/budget-forecasts endpoint ───────────────────────────────
    if path == "/api/budget-forecasts" && parts.method == Method::GET {
        let result = if let Ok(conn) = state.db.lock() {
            match db::get_budget_forecasts(&conn) {
                Ok(forecasts) => serde_json::json!({
                    "status": "ok",
                    "forecasts": forecasts,
                }),
                Err(e) => serde_json::json!({"status": "error", "message": e.to_string()}),
            }
        } else {
            serde_json::json!({"status": "error", "message": "database lock failed"})
        };

        return Ok(json_response(StatusCode::OK, result));
    }

    // ── /api/budgets endpoint ─────────────────────────────────────────
    if path == "/api/budgets" && parts.method == Method::GET {
        let result = if let Ok(conn) = state.db.lock() {
            match db::check_budgets(&conn) {
                Ok(statuses) => serde_json::json!({
                    "status": "ok",
                    "budgets": statuses,
                }),
                Err(e) => serde_json::json!({"status": "error", "message": e.to_string()}),
            }
        } else {
            serde_json::json!({"status": "error", "message": "database lock failed"})
        };

        return Ok(json_response(StatusCode::OK, result));
    }

    if path == "/api/context-audit" && parts.method == Method::GET {
        let time_range = parts
            .uri
            .query()
            .and_then(|q| {
                url::form_urlencoded::parse(q.as_bytes())
                    .find(|(k, _)| k == "range")
                    .map(|(_, v)| v.into_owned())
            })
            .unwrap_or_else(|| "today".to_string());

        let result = if let Ok(conn) = state.db.lock() {
            match db::get_context_audit_snapshot(&conn, &time_range) {
                Ok(snapshot) => serde_json::json!({
                    "status": "ok",
                    "context_audit": snapshot,
                }),
                Err(e) => serde_json::json!({"status": "error", "message": e.to_string()}),
            }
        } else {
            serde_json::json!({"status": "error", "message": "database lock failed"})
        };

        return Ok(json_response(StatusCode::OK, result));
    }

    let provider = detect_provider(&parts.headers, &path);
    let forward_path = build_forward_path(&provider, &path);
    let target_url = format!("{}{}{}", provider.base_url, forward_path, query);

    // Detect source tag from headers
    let source_tag = detect_source_tag(&parts.headers);

    // Read request body
    let body_bytes = match axum::body::to_bytes(body, 10 * 1024 * 1024).await {
        Ok(b) => b,
        Err(_) => return Err(StatusCode::BAD_REQUEST),
    };

    let body_json_result: Result<Value, _> = serde_json::from_slice(&body_bytes);
    let mut body_json = body_json_result.unwrap_or(Value::Null);
    let has_json_body = body_json != Value::Null;
    let model = extract_model(&body_json, &provider.name, &path);
    let is_streaming = is_streaming_request(&body_json);

    eprintln!(
        "[TokenPulse] {} {} → {} (provider: {}, model: {}, streaming: {})",
        parts.method,
        path,
        redact_url_secrets(&target_url),
        provider.name,
        model,
        is_streaming
    );

    // Inject `stream_options: {include_usage: true}` for OpenAI-compatible
    // **Chat Completions** streaming requests so the in-stream usage block is
    // emitted by the upstream and we can read it for accounting.
    //
    // Gating rules:
    //   1. Skip non-OpenAI-shaped providers entirely. They never accepted
    //      stream_options (anthropic uses message_delta events; google uses
    //      usageMetadata; ollama emits prompt_eval_count/eval_count natively).
    //   2. Skip OpenAI Responses API endpoints. The Responses API ships usage
    //      in the terminal `response.completed` event natively and rejects
    //      `stream_options` with HTTP 400. The most painful instance of this
    //      is the ChatGPT Plus Codex OAuth backend at
    //      `chatgpt.com/backend-api/codex/responses`.
    //
    // The path-shape check (`is_responses_api_path`) is the durable guard:
    // any future Responses API variant (Azure, openai/v1/responses, etc.) is
    // automatically excluded without having to add it to a hand-maintained
    // provider name list.
    let is_responses_api = is_responses_api_path(&path);
    let provider_excluded = matches!(provider.name.as_str(), "anthropic" | "google" | "ollama");
    if is_streaming && !provider_excluded && !is_responses_api {
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
        // Also strip accept-encoding: the proxy reads the raw byte stream for SSE
        // parsing, so compressed responses would break token extraction.
        // reqwest's bytes_stream() does NOT auto-decompress.
        if matches!(
            name_str,
            "host" | "connection" | "transfer-encoding" | "content-length" | "accept-encoding"
        ) {
            continue;
        }
        if let Ok(val) = reqwest::header::HeaderValue::from_bytes(value.as_bytes()) {
            if let Ok(header_name) =
                reqwest::header::HeaderName::from_bytes(name.as_str().as_bytes())
            {
                forward_headers.insert(header_name, val);
            }
        }
    }
    eprintln!("[TokenPulse] Forwarding {} headers", forward_headers.len());

    let method = match parts.method {
        Method::GET => reqwest::Method::GET,
        Method::POST => reqwest::Method::POST,
        Method::PUT => reqwest::Method::PUT,
        Method::DELETE => reqwest::Method::DELETE,
        Method::PATCH => reqwest::Method::PATCH,
        _ => reqwest::Method::POST,
    };

    let forward_req = state
        .http_client
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
        }
        Err(e) => {
            eprintln!(
                "[TokenPulse] ERROR forwarding to {}: {}",
                redact_url_secrets(&target_url),
                e
            );
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
                source_tag: source_tag.clone(),
                error_message: Some(redact_secrets_in_text(&e.to_string())),
                provider_type: get_provider_type(&provider.name),
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
        let resp_bytes = response
            .bytes()
            .await
            .map_err(|_| StatusCode::BAD_GATEWAY)?;
        let latency_ms = start_time.elapsed().as_millis() as i64;
        let error_text = String::from_utf8_lossy(&resp_bytes).to_string();
        let truncated = &error_text[..error_text.len().min(200)];
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
            source_tag: source_tag.clone(),
            error_message: Some(redact_secrets_in_text(&format!(
                "HTTP {}: {}",
                status.as_u16(),
                truncated
            ))),
            provider_type: get_provider_type(&provider.name),
        };
        if let Ok(conn) = state.db.lock() {
            let _ = insert_request(&conn, &record);
        }
        return Ok(response_with_headers(
            status,
            &resp_headers,
            Body::from(resp_bytes),
            false,
        ));
    }

    if is_streaming {
        // Stream response back, collecting chunks to find usage
        let mut stream = response.bytes_stream();
        let (tx, rx) = tokio::sync::mpsc::channel::<Result<Bytes, std::io::Error>>(100);
        let provider_name = provider.name.clone();
        let provider_type = get_provider_type(&provider.name);
        let db = state.db.clone();
        let model_clone = model.clone();
        let is_responses_api_stream = is_responses_api;

        tokio::spawn(async move {
            let mut last_chunk_json: Option<Value> = None;
            let mut ttft_ms: i64 = -1;
            let mut first_chunk = true;
            // For Anthropic streaming: accumulate tokens across event types
            let mut anthropic_input: i64 = 0;
            let mut anthropic_output: i64 = 0;
            let mut anthropic_cached: i64 = 0;
            // For OpenAI Responses API streaming (incl. Codex OAuth): the usage
            // block lives in the terminal `response.completed` event. We track
            // it as it arrives so it survives the post-stream extraction step.
            let mut responses_api_usage: Option<(i64, i64, i64, i64)> = None;
            // SSE line buffer. A single SSE event can be much larger than one
            // TCP/HTTP chunk (the Codex `response.completed` event is ~1.5 KB),
            // so we cannot rely on each chunk containing complete SSE events.
            // We accumulate UTF-8 text here and only consume up to the last
            // newline on each iteration; the trailing partial line carries over.
            let mut sse_buffer = String::new();
            let mut current_sse_event: Option<String> = None;
            let mut current_sse_data: Vec<String> = Vec::new();

            while let Some(chunk_result) = stream.next().await {
                match chunk_result {
                    Ok(chunk) => {
                        if first_chunk {
                            ttft_ms = start_time.elapsed().as_millis() as i64;
                            first_chunk = false;
                        }

                        // Append new bytes to the line buffer (lossy UTF-8 is
                        // safe here: SSE is text/event-stream and any invalid
                        // bytes would already be a protocol violation).
                        sse_buffer.push_str(&String::from_utf8_lossy(&chunk));

                        // Process every complete line in the buffer. Anything
                        // after the last newline is a partial line that has to
                        // wait for the next chunk.
                        let last_newline = sse_buffer.rfind('\n');
                        let to_process = if let Some(idx) = last_newline {
                            // Drain `[0..=idx]` from the buffer; keep the rest.
                            let drained: String = sse_buffer.drain(..=idx).collect();
                            drained
                        } else {
                            String::new()
                        };

                        for raw_line in to_process.lines() {
                            let line = raw_line.trim_end_matches('\r');
                            if line.is_empty() {
                                if !current_sse_data.is_empty() {
                                    let event_data = current_sse_data.join("\n");
                                    handle_stream_sse_event(
                                        &provider_name,
                                        &model_clone,
                                        is_responses_api_stream,
                                        current_sse_event.as_deref(),
                                        &event_data,
                                        &mut last_chunk_json,
                                        &mut responses_api_usage,
                                        &mut anthropic_input,
                                        &mut anthropic_output,
                                        &mut anthropic_cached,
                                    );
                                    current_sse_data.clear();
                                }
                                current_sse_event = None;
                                continue;
                            }

                            if let Some(event_name) = extract_sse_field_value(line, "event:") {
                                current_sse_event = Some(event_name.to_string());
                                continue;
                            }

                            if let Some(data) = extract_sse_field_value(line, "data:") {
                                current_sse_data.push(data.to_string());
                            }
                        }

                        let _ = tx.send(Ok(chunk)).await;
                    }
                    Err(e) => {
                        let error_text = e.to_string();
                        eprintln!(
                            "[TokenPulse] streaming error from {} {}: {}",
                            provider_name, model_clone, error_text
                        );
                        let _ = tx
                            .send(Err(std::io::Error::new(
                                std::io::ErrorKind::Other,
                                error_text.clone(),
                            )))
                            .await;

                        let latency_ms = start_time.elapsed().as_millis() as i64;
                        let partial_record = RequestRecord {
                            id: None,
                            timestamp: start_timestamp.clone(),
                            provider: provider_name.clone(),
                            model: model_clone.clone(),
                            input_tokens: anthropic_input,
                            output_tokens: anthropic_output,
                            cached_tokens: anthropic_cached,
                            reasoning_tokens: 0,
                            cost_usd: 0.0,
                            latency_ms,
                            tokens_per_second: 0.0,
                            time_to_first_token_ms: ttft_ms,
                            is_streaming: true,
                            is_complete: false,
                            source_tag: source_tag.clone(),
                            error_message: Some(redact_secrets_in_text(&format!(
                                "stream interrupted: {}",
                                error_text
                            ))),
                            provider_type: provider_type.clone(),
                        };
                        if let Ok(conn) = db.lock() {
                            let _ = insert_request(&conn, &partial_record);
                        }
                        return;
                    }
                }
            }

            // Flush any trailing line that didn't have a final newline. Most
            // SSE producers terminate events with `\n\n`, but defensive
            // flushing is cheap and prevents the very last event being lost
            // if the upstream omits the trailing newline.
            if !sse_buffer.is_empty() {
                for raw_line in sse_buffer.lines() {
                    let line = raw_line.trim_end_matches('\r');
                    if line.is_empty() {
                        if !current_sse_data.is_empty() {
                            let event_data = current_sse_data.join("\n");
                            handle_stream_sse_event(
                                &provider_name,
                                &model_clone,
                                is_responses_api_stream,
                                current_sse_event.as_deref(),
                                &event_data,
                                &mut last_chunk_json,
                                &mut responses_api_usage,
                                &mut anthropic_input,
                                &mut anthropic_output,
                                &mut anthropic_cached,
                            );
                            current_sse_data.clear();
                        }
                        current_sse_event = None;
                        continue;
                    }

                    if let Some(event_name) = extract_sse_field_value(line, "event:") {
                        current_sse_event = Some(event_name.to_string());
                        continue;
                    }

                    if let Some(data) = extract_sse_field_value(line, "data:") {
                        current_sse_data.push(data.to_string());
                    }
                }
            }

            if !current_sse_data.is_empty() {
                let event_data = current_sse_data.join("\n");
                handle_stream_sse_event(
                    &provider_name,
                    &model_clone,
                    is_responses_api_stream,
                    current_sse_event.as_deref(),
                    &event_data,
                    &mut last_chunk_json,
                    &mut responses_api_usage,
                    &mut anthropic_input,
                    &mut anthropic_output,
                    &mut anthropic_cached,
                );
            }

            // Extract usage. Resolution order:
            //   1. Anthropic accumulator (message_start + message_delta).
            //   2. OpenAI Responses API accumulator (response.completed event).
            //   3. Generic last-chunk extractor (Chat Completions usage block,
            //      Ollama native fields, etc.).
            let (input_tokens, output_tokens, cached_tokens, reasoning_tokens) =
                if provider_name == "anthropic" && (anthropic_input > 0 || anthropic_output > 0) {
                    (anthropic_input, anthropic_output, anthropic_cached, 0)
                } else if let Some(usage) = responses_api_usage {
                    usage
                } else if let Some(ref json) = last_chunk_json {
                    extract_usage(json, &provider_name)
                } else {
                    (0, 0, 0, 0)
                };

            let latency_ms = start_time.elapsed().as_millis() as i64;
            let cost = if let Ok(conn) = db.lock() {
                calculate_cost_with_db(
                    &conn,
                    &model_clone,
                    Some(&provider_name),
                    input_tokens as u32,
                    output_tokens as u32,
                )
            } else {
                0.0
            };
            let tps = if latency_ms > 0 && output_tokens > 0 {
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
                source_tag: source_tag.clone(),
                error_message: None,
                provider_type,
            };

            if let Ok(conn) = db.lock() {
                let _ = insert_request(&conn, &record);
            }
        });

        let stream_body = Body::from_stream(tokio_stream::wrappers::ReceiverStream::new(rx));

        Ok(response_with_headers(
            status,
            &resp_headers,
            stream_body,
            false,
        ))
    } else {
        // Non-streaming: read full response
        let resp_bytes = response
            .bytes()
            .await
            .map_err(|_| StatusCode::BAD_GATEWAY)?;
        let latency_ms = start_time.elapsed().as_millis() as i64;

        if let Ok(json) = serde_json::from_slice::<Value>(&resp_bytes) {
            let (input_tokens, output_tokens, cached_tokens, reasoning_tokens) =
                extract_usage(&json, &provider.name);
            let cost = if let Ok(conn) = state.db.lock() {
                calculate_cost_with_db(
                    &conn,
                    &model,
                    Some(&provider.name),
                    input_tokens as u32,
                    output_tokens as u32,
                )
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
                source_tag: source_tag.clone(),
                error_message: None,
                provider_type: get_provider_type(&provider.name),
            };

            if let Ok(conn) = state.db.lock() {
                let _ = insert_request(&conn, &record);
            }
        }

        Ok(response_with_headers(
            status,
            &resp_headers,
            Body::from(resp_bytes),
            true,
        ))
    }
}

pub async fn start_proxy_server(
    db: Arc<Mutex<rusqlite::Connection>>,
    proxy_running: Arc<AtomicBool>,
    proxy_paused: Arc<AtomicBool>,
) {
    let http_client = match Client::builder()
        .timeout(std::time::Duration::from_secs(300))
        .build()
    {
        Ok(client) => client,
        Err(err) => {
            eprintln!("[TokenPulse] Failed to build HTTP client: {}", err);
            proxy_running.store(false, Ordering::SeqCst);
            return;
        }
    };

    let state = AppState {
        db,
        http_client,
        proxy_paused,
    };

    let cors = build_cors_layer();

    let app = Router::new()
        .fallback(any(proxy_handler))
        .layer(cors)
        .with_state(state);

    match tokio::net::TcpListener::bind("127.0.0.1:4100").await {
        Ok(listener) => {
            proxy_running.store(true, Ordering::SeqCst);
            eprintln!("TokenPulse proxy listening on http://127.0.0.1:4100");
            axum::serve(listener, app).await.ok();
            proxy_running.store(false, Ordering::SeqCst);
        }
        Err(e) => {
            eprintln!(
                "Failed to bind proxy port 4100: {}. Is another instance running?",
                e
            );
            proxy_running.store(false, Ordering::SeqCst);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::{extract_sse_field_value, handle_stream_sse_event};
    use serde_json::json;

    #[test]
    fn sse_field_value_accepts_optional_space_after_colon() {
        assert_eq!(
            extract_sse_field_value("data: {\"ok\":true}", "data:"),
            Some("{\"ok\":true}")
        );
        assert_eq!(
            extract_sse_field_value("data:{\"ok\":true}", "data:"),
            Some("{\"ok\":true}")
        );
        assert_eq!(
            extract_sse_field_value("event: message_start", "event:"),
            Some("message_start")
        );
    }

    #[test]
    fn anthropic_stream_usage_accumulates_from_documented_events() {
        let mut last_chunk_json = None;
        let mut responses_api_usage = None;
        let mut anthropic_input = 0;
        let mut anthropic_output = 0;
        let mut anthropic_cached = 0;

        handle_stream_sse_event(
            "anthropic",
            "claude-opus-4-6",
            false,
            Some("message_start"),
            &json!({
                "type": "message_start",
                "message": {
                    "usage": {
                        "input_tokens": 472,
                        "output_tokens": 2,
                        "cache_read_input_tokens": 128
                    }
                }
            })
            .to_string(),
            &mut last_chunk_json,
            &mut responses_api_usage,
            &mut anthropic_input,
            &mut anthropic_output,
            &mut anthropic_cached,
        );

        handle_stream_sse_event(
            "anthropic",
            "claude-opus-4-6",
            false,
            Some("message_delta"),
            &json!({
                "type": "message_delta",
                "usage": {
                    "output_tokens": 89
                }
            })
            .to_string(),
            &mut last_chunk_json,
            &mut responses_api_usage,
            &mut anthropic_input,
            &mut anthropic_output,
            &mut anthropic_cached,
        );

        assert_eq!(anthropic_input, 472);
        assert_eq!(anthropic_output, 89);
        assert_eq!(anthropic_cached, 128);
        assert_eq!(
            last_chunk_json
                .as_ref()
                .and_then(|json| json.get("type"))
                .and_then(|value| value.as_str()),
            Some("message_delta")
        );
        assert!(responses_api_usage.is_none());
    }
}
