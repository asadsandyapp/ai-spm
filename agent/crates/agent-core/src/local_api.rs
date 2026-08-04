//! Localhost API for managed browser extension + prompt inspection.
//!
//! Enterprise deployment:
//! - Chrome enterprise policy force-installs the extension (zero user action)
//! - Extension captures web-UI prompts in-page and POSTs to /inspect
//! - Agent serves extension CRX + update manifest from /extension/*

use std::convert::Infallible;
use std::net::SocketAddr;
use std::path::Path;
use std::sync::Arc;

use http_body_util::{BodyExt, Full};
use hyper::body::Bytes;
use hyper::server::conn::http1;
use hyper::service::service_fn;
use hyper::{Method, Request, Response, StatusCode};
use hyper_util::rt::TokioIo;
use serde::{Deserialize, Serialize};
use tokio::net::TcpListener;
use tokio::sync::watch;
use tracing::{debug, info, warn};

use crate::gateway::{GatewayClient, PromptRequest, WebAuditRequest};
use crate::proxy::ProxyError;
use crate::status::SharedAgentStatus;

const DEFAULT_CRX_PATH: &str = "/opt/ai-spm/ai-spm-prompt-guard.crx";
const DEFAULT_EXT_ID_PATH: &str = "/opt/ai-spm/extension-id";
const DEFAULT_EXT_MANIFEST_PATH: &str = "/opt/ai-spm/browser-extension/manifest.json";

#[derive(Debug, Deserialize)]
struct InspectRequest {
    #[serde(default)]
    provider: String,
    #[serde(default)]
    model: String,
    messages: Vec<InspectMessage>,
}

#[derive(Debug, Deserialize)]
struct InspectMessage {
    #[serde(default = "default_role")]
    role: String,
    content: String,
}

fn default_role() -> String {
    "user".to_string()
}

#[derive(Debug, Deserialize)]
struct WebAuditBody {
    #[serde(default = "default_chatgpt_provider")]
    provider: String,
    #[serde(default = "default_web_model")]
    model: String,
    masked_content: String,
    #[serde(default)]
    original_content: Option<String>,
    #[serde(default)]
    pii_entities: Vec<String>,
    #[serde(default)]
    pii_hit_count: u32,
    #[serde(default = "default_web_source")]
    source: String,
}

fn default_chatgpt_provider() -> String {
    "chatgpt".to_string()
}

fn default_web_model() -> String {
    "web-ui".to_string()
}

fn default_web_source() -> String {
    "web_mitm".to_string()
}

#[derive(Debug, Serialize)]
struct ErrorResponse {
    error: String,
    blocked_reason: Option<String>,
}

#[derive(Debug, Serialize)]
struct InspectResponse {
    decision: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    masked_messages: Option<Vec<serde_json::Value>>,
    #[serde(skip_serializing_if = "Option::is_none")]
    blocked_reason: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    block_code: Option<String>,
}

/// Run the localhost API until shutdown.
pub async fn run_local_api(
    listen: SocketAddr,
    gateway: Arc<GatewayClient>,
    status: SharedAgentStatus,
    mut shutdown: watch::Receiver<bool>,
) -> Result<(), ProxyError> {
    let listener = TcpListener::bind(listen).await.map_err(ProxyError::Bind)?;
    info!(
        %listen,
        "local API listening — prompt inspection + managed extension distribution"
    );

    loop {
        tokio::select! {
            _ = shutdown.changed() => {
                if *shutdown.borrow() {
                    info!("local API shutting down");
                    return Ok(());
                }
            }
            accept = listener.accept() => {
                let (stream, _peer) = accept.map_err(ProxyError::Accept)?;
                let gateway = Arc::clone(&gateway);
                let status = Arc::clone(&status);
                tokio::spawn(async move {
                    let io = TokioIo::new(stream);
                    let service = service_fn(move |req| {
                        let gateway = Arc::clone(&gateway);
                        let status = Arc::clone(&status);
                        async move { handle(gateway, status, req).await }
                    });
                    if let Err(err) = http1::Builder::new().serve_connection(io, service).await {
                        debug!(error = %err, "local API connection closed");
                    }
                });
            }
        }
    }
}

async fn handle(
    gateway: Arc<GatewayClient>,
    status: SharedAgentStatus,
    req: Request<hyper::body::Incoming>,
) -> Result<Response<Full<Bytes>>, Infallible> {
    if req.method() == Method::OPTIONS {
        return Ok(cors(Response::builder()
            .status(StatusCode::NO_CONTENT)
            .body(Full::new(Bytes::new()))
            .unwrap()));
    }

    let method = req.method();
    let path = req.uri().path();

    match (method, path) {
        (&Method::GET, "/status") => Ok(cors(json_response(StatusCode::OK, &status.snapshot()))),
        (&Method::GET, "/extension/updates.xml") => Ok(cors(serve_updates_xml())),
        (&Method::GET, "/extension/ai-spm-prompt-guard.crx") => Ok(cors(serve_crx().await)),
        (&Method::GET, "/extension/hook-ping") => Ok(cors(serve_hook_ping(req.uri().query()))),
        (&Method::POST, "/inspect") => handle_inspect(gateway, status, req).await,
        (&Method::POST, "/web-audit") => handle_web_audit(gateway, req).await,
        _ => Ok(cors(json_response(
            StatusCode::NOT_FOUND,
            &serde_json::json!({"error": "not found"}),
        ))),
    }
}

/// Extension content-script heartbeat — proves hooks injected and SW can reach local_api.
fn serve_hook_ping(query: Option<&str>) -> Response<Full<Bytes>> {
    let host = query
        .unwrap_or("")
        .split('&')
        .find_map(|pair| {
            let mut parts = pair.splitn(2, '=');
            match (parts.next(), parts.next()) {
                (Some("host"), Some(v)) => Some(v.to_string()),
                _ => None,
            }
        })
        .unwrap_or_else(|| "unknown".to_string());
    let host = urlencoding_decode(&host);
    info!(host = %host, "extension hooks alive on AI web UI frame");
    json_response(
        StatusCode::OK,
        &serde_json::json!({"ok": true, "host": host}),
    )
}

fn urlencoding_decode(raw: &str) -> String {
    let bytes: Vec<u8> = raw
        .as_bytes()
        .iter()
        .copied()
        .collect();
    // Minimal %XX decode for hostname query values (no + → space needed for hosts).
    let mut out = Vec::with_capacity(bytes.len());
    let mut i = 0;
    while i < bytes.len() {
        if bytes[i] == b'%' && i + 2 < bytes.len() {
            let h = |c: u8| -> Option<u8> {
                match c {
                    b'0'..=b'9' => Some(c - b'0'),
                    b'a'..=b'f' => Some(c - b'a' + 10),
                    b'A'..=b'F' => Some(c - b'A' + 10),
                    _ => None,
                }
            };
            if let (Some(a), Some(b)) = (h(bytes[i + 1]), h(bytes[i + 2])) {
                out.push((a << 4) | b);
                i += 3;
                continue;
            }
        }
        out.push(bytes[i]);
        i += 1;
    }
    String::from_utf8(out).unwrap_or_else(|_| raw.to_string())
}

async fn handle_inspect(
    gateway: Arc<GatewayClient>,
    status: SharedAgentStatus,
    req: Request<hyper::body::Incoming>,
) -> Result<Response<Full<Bytes>>, Infallible> {
    let body = match req.into_body().collect().await {
        Ok(b) => b.to_bytes(),
        Err(_) => {
            return Ok(cors(json_response(
                StatusCode::BAD_REQUEST,
                &serde_json::json!({"error": "invalid body"}),
            )))
        }
    };

    let parsed: InspectRequest = match serde_json::from_slice(&body) {
        Ok(p) => p,
        Err(err) => {
            return Ok(cors(json_response(
                StatusCode::BAD_REQUEST,
                &serde_json::json!({"error": format!("invalid json: {err}")}),
            )))
        }
    };

    if parsed.messages.is_empty() {
        return Ok(cors(json_response(
            StatusCode::OK,
            &InspectResponse {
                decision: "allowed".to_string(),
                masked_messages: None,
                blocked_reason: None,
                block_code: None,
            },
        )));
    }

    let provider = if parsed.provider.is_empty() {
        "openai".to_string()
    } else {
        parsed.provider.clone()
    };
    let model = if parsed.model.is_empty() {
        default_model_for_provider(&provider)
    } else {
        parsed.model.clone()
    };
    let messages: Vec<serde_json::Value> = parsed
        .messages
        .iter()
        .map(|m| serde_json::json!({"role": m.role, "content": m.content}))
        .collect();

    let prompt = PromptRequest {
        provider,
        model,
        messages,
        max_tokens: None,
        inspect_only: true,
    };

    match gateway.submit_prompt(&prompt).await {
        Ok(resp) => {
            info!(decision = %resp.decision, "web-UI prompt inspected");
            if resp.decision == "blocked" {
                status.record_block(
                    prompt.provider.clone(),
                    resp.blocked_reason
                        .clone()
                        .unwrap_or_else(|| "Request blocked by AI-SPM policy".to_string()),
                );
            }
            Ok(cors(json_response(
                StatusCode::OK,
                &InspectResponse {
                    decision: resp.decision,
                    masked_messages: resp.masked_messages,
                    blocked_reason: resp.blocked_reason,
                    block_code: resp.block_code,
                },
            )))
        }
        Err(err) => {
            warn!(error = %err, "gateway inspection failed");
            Ok(cors(json_response(
                StatusCode::OK,
                &InspectResponse {
                    decision: "allowed".to_string(),
                    masked_messages: None,
                    blocked_reason: None,
                    block_code: None,
                },
            )))
        }
    }
}

async fn handle_web_audit(
    gateway: Arc<GatewayClient>,
    req: Request<hyper::body::Incoming>,
) -> Result<Response<Full<Bytes>>, Infallible> {
    let body = match req.into_body().collect().await {
        Ok(b) => b.to_bytes(),
        Err(_) => {
            return Ok(cors(json_response(
                StatusCode::BAD_REQUEST,
                &serde_json::json!({"error": "invalid body"}),
            )))
        }
    };

    let parsed: WebAuditBody = match serde_json::from_slice(&body) {
        Ok(p) => p,
        Err(err) => {
            return Ok(cors(json_response(
                StatusCode::BAD_REQUEST,
                &serde_json::json!({"error": format!("invalid json: {err}")}),
            )))
        }
    };

    if parsed.masked_content.trim().is_empty() {
        return Ok(cors(json_response(
            StatusCode::BAD_REQUEST,
            &serde_json::json!({"error": "masked_content required"}),
        )));
    }

    let audit = WebAuditRequest {
        provider: if parsed.provider.is_empty() {
            "chatgpt".to_string()
        } else {
            parsed.provider
        },
        model: if parsed.model.is_empty() {
            "web-ui".to_string()
        } else {
            parsed.model
        },
        masked_content: parsed.masked_content.chars().take(2000).collect(),
        original_content: parsed
            .original_content
            .map(|s| s.chars().take(2000).collect()),
        pii_entities: parsed.pii_entities,
        pii_hit_count: parsed.pii_hit_count,
        source: if parsed.source.is_empty() {
            "web_mitm".to_string()
        } else {
            parsed.source
        },
    };

    match gateway.submit_web_audit(&audit).await {
        Ok(resp) => {
            info!(
                event_type = %resp.event_type,
                audit_id = %resp.audit_event_id,
                "web MITM audit recorded"
            );
            Ok(cors(json_response(
                StatusCode::OK,
                &serde_json::json!({
                    "audit_event_id": resp.audit_event_id,
                    "event_type": resp.event_type,
                }),
            )))
        }
        Err(err) => {
            // Fail-open: masking already happened; audit must not break chat.
            warn!(error = %err, "web MITM audit failed (fail-open)");
            Ok(cors(json_response(
                StatusCode::OK,
                &serde_json::json!({"ok": false, "error": err.to_string()}),
            )))
        }
    }
}

fn read_extension_version() -> String {
    let path = std::env::var("AISPM_EXTENSION_MANIFEST")
        .unwrap_or_else(|_| DEFAULT_EXT_MANIFEST_PATH.to_string());
    if let Ok(content) = std::fs::read_to_string(&path) {
        if let Ok(json) = serde_json::from_str::<serde_json::Value>(&content) {
            if let Some(version) = json.get("version").and_then(|v| v.as_str()) {
                return version.to_string();
            }
        }
    } else {
        tracing::warn!(
            path = %path,
            "extension manifest unreadable — Chrome updates.xml version may be wrong"
        );
    }
    // Prefer on-disk updates.xml written by reconcile over a stale hardcoded default.
    if let Ok(xml) = std::fs::read_to_string("/opt/ai-spm/updates.xml") {
        if let Some(v) = xml.split("version='").nth(1).and_then(|s| s.split('\'').next()) {
            if !v.is_empty() {
                return v.to_string();
            }
        }
    }
    "0.0.0".to_string()
}

fn serve_updates_xml() -> Response<Full<Bytes>> {
    let ext_id = read_extension_id();
    let version = read_extension_version();
    let xml = format!(
        r#"<?xml version='1.0' encoding='UTF-8'?>
<gupdate xmlns='http://www.google.com/update2/response' protocol='2.0'>
  <app appid='{ext_id}'>
    <updatecheck codebase='http://127.0.0.1:8092/extension/ai-spm-prompt-guard.crx' version='{version}' />
  </app>
</gupdate>"#
    );
    Response::builder()
        .status(StatusCode::OK)
        .header("content-type", "application/xml")
        .body(Full::new(Bytes::from(xml)))
        .unwrap()
}

async fn serve_crx() -> Response<Full<Bytes>> {
    let path = std::env::var("AISPM_EXTENSION_CRX")
        .unwrap_or_else(|_| DEFAULT_CRX_PATH.to_string());
    match tokio::fs::read(&path).await {
        Ok(bytes) => Response::builder()
            .status(StatusCode::OK)
            .header("content-type", "application/x-chrome-extension")
            .body(Full::new(Bytes::from(bytes)))
            .unwrap(),
        Err(err) => {
            warn!(path = %path, error = %err, "extension CRX not found");
            json_response(
                StatusCode::NOT_FOUND,
                &serde_json::json!({"error": "extension not packaged yet — run install-agent.sh"}),
            )
        }
    }
}

fn read_extension_id() -> String {
    let path = std::env::var("AISPM_EXTENSION_ID_FILE")
        .unwrap_or_else(|_| DEFAULT_EXT_ID_PATH.to_string());
    std::fs::read_to_string(path)
        .map(|s| s.trim().to_string())
        .unwrap_or_else(|_| "placeholderextensionid".to_string())
}

fn default_model_for_provider(provider: &str) -> String {
    match provider {
        "anthropic" => "claude-3-5-sonnet".to_string(),
        "gemini" => "gemini-1.5-pro".to_string(),
        _ => "gpt-4o".to_string(),
    }
}

fn json_response<T: Serialize>(status: StatusCode, body: &T) -> Response<Full<Bytes>> {
    let bytes = serde_json::to_vec(body).unwrap_or_default();
    Response::builder()
        .status(status)
        .header("content-type", "application/json")
        .body(Full::new(Bytes::from(bytes)))
        .unwrap()
}

fn cors(mut resp: Response<Full<Bytes>>) -> Response<Full<Bytes>> {
    let headers = resp.headers_mut();
    headers.insert("access-control-allow-origin", "*".parse().unwrap());
    headers.insert(
        "access-control-allow-methods",
        "GET, POST, OPTIONS".parse().unwrap(),
    );
    headers.insert(
        "access-control-allow-headers",
        "content-type".parse().unwrap(),
    );
    resp
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn updates_xml_contains_appid() {
        let resp = serve_updates_xml();
        assert_eq!(resp.status(), StatusCode::OK);
    }
}
