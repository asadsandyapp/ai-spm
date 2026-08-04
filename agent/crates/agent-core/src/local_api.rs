//! Localhost bridge for web-UI MITM audit.
//!
//! Enterprise deployment:
//! - mitmproxy masks PII on ChatGPT / Claude / Gemini web UIs
//! - Addon POSTs masked results to `/web-audit` on 127.0.0.1:8092
//! - Agent forwards to gateway `POST /agent/v1/web-audit` (fail-open)

use std::convert::Infallible;
use std::net::SocketAddr;
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

use crate::gateway::{GatewayClient, WebAuditRequest};
use crate::proxy::ProxyError;

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

/// Run the localhost web-audit bridge until shutdown.
pub async fn run_local_api(
    listen: SocketAddr,
    gateway: Arc<GatewayClient>,
    mut shutdown: watch::Receiver<bool>,
) -> Result<(), ProxyError> {
    let listener = TcpListener::bind(listen).await.map_err(ProxyError::Bind)?;
    info!(%listen, "local API listening — web-audit bridge for mitmproxy");

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
                tokio::spawn(async move {
                    let io = TokioIo::new(stream);
                    let service = service_fn(move |req| {
                        let gateway = Arc::clone(&gateway);
                        async move { handle(gateway, req).await }
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
        (&Method::POST, "/web-audit") => handle_web_audit(gateway, req).await,
        _ => Ok(cors(json_response(
            StatusCode::NOT_FOUND,
            &serde_json::json!({"error": "not found"}),
        ))),
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
