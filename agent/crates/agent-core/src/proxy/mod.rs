//! Local HTTP/HTTPS MITM proxy for intercepting AI provider traffic.
//!
//! Handles plain HTTP requests and HTTPS via CONNECT + TLS termination using a
//! locally generated root CA. Intercepted prompt bodies are sent to the AI-SPM
//! gateway security pipeline before being forwarded (possibly masked) upstream.

mod ca;
mod mitm;
mod parser;
mod sni;
mod tcp;
mod transparent;
mod upstream;

use std::convert::Infallible;
use std::net::SocketAddr;
use std::path::PathBuf;
use std::sync::Arc;

use http_body_util::{BodyExt, Full};
use hyper::body::Bytes;
use hyper::server::conn::http1;
use hyper::service::service_fn;
use hyper::{Method, Request, Response, StatusCode, Uri};
use hyper_util::rt::TokioIo;
use thiserror::Error;
use tokio::io::copy_bidirectional;
use tokio::net::TcpListener;
use tokio::sync::watch;
use tracing::{debug, info, warn};

use crate::gateway::{GatewayClient, PromptRequest};
use ca::MitmCertificateAuthority;
use upstream::build_chrome_upstream_client;
use tcp::connect_marked;

pub use ca::{CaError, MitmCertificateAuthority as CaAuthority};
pub use tcp::DEFAULT_SOCKET_MARK;
pub use transparent::run_transparent_proxy;

fn normalize_host(host: &str) -> String {
    host.split(':')
        .next()
        .unwrap_or(host)
        .trim_end_matches('.')
        .to_ascii_lowercase()
}

fn host_matches(host: &str, domains: &[String]) -> bool {
    let host = normalize_host(host);
    domains
        .iter()
        .any(|domain| host == *domain || host.ends_with(&format!(".{domain}")))
}

fn host_matches_str(host: &str, domains: &[&str]) -> bool {
    let host = normalize_host(host);
    domains
        .iter()
        .any(|domain| host == *domain || host.ends_with(&format!(".{domain}")))
}

/// Returns true if the host matches a default MITM AI provider domain.
///
/// Uses [`DEFAULT_MITM_DOMAINS`]; for runtime-configured behavior use
/// [`ProxyState::should_mitm`].
pub fn should_intercept(host: &str) -> bool {
    let defaults: Vec<String> = DEFAULT_MITM_DOMAINS.iter().map(|s| s.to_string()).collect();
    host_matches(host, &defaults)
}

/// Build shared proxy state (CA + upstream client) for explicit and transparent modes.
pub fn build_proxy_state(
    gateway: Arc<GatewayClient>,
    ca_dir: PathBuf,
    mitm_domains: Vec<String>,
) -> Result<Arc<ProxyState>, ProxyError> {
    ensure_crypto_provider();
    let ca = Arc::new(MitmCertificateAuthority::load_or_create(&ca_dir)?);
    let upstream =
        build_chrome_upstream_client().map_err(|e| ProxyError::Upstream(e.to_string()))?;
    let mitm_domains = if mitm_domains.is_empty() {
        DEFAULT_MITM_DOMAINS.iter().map(|s| s.to_string()).collect()
    } else {
        mitm_domains
    };
    info!(
        ?mitm_domains,
        "MITM domain set — AI API hosts at network layer; CF web UIs via mitmproxy"
    );
    Ok(Arc::new(ProxyState {
        gateway,
        ca,
        upstream,
        mitm_domains,
    }))
}

/// Run the optional explicit HTTP CONNECT proxy (legacy / dev mode).
pub async fn run_explicit_proxy(
    listen: SocketAddr,
    state: Arc<ProxyState>,
    mut shutdown: watch::Receiver<bool>,
) -> Result<(), ProxyError> {
    info!(
        %listen,
        ca_cert = %state.ca.ca_cert_path().display(),
        domains = ?state.mitm_domains,
        "explicit HTTP proxy listening (legacy mode)"
    );

    let listener = TcpListener::bind(listen).await.map_err(ProxyError::Bind)?;

    loop {
        tokio::select! {
            _ = shutdown.changed() => {
                if *shutdown.borrow() {
                    info!("explicit proxy shutting down");
                    return Ok(());
                }
            }
            accept = listener.accept() => {
                let (stream, peer) = accept.map_err(ProxyError::Accept)?;
                let state = Arc::clone(&state);
                tokio::spawn(async move {
                    let io = TokioIo::new(stream);
                    let service = service_fn(move |req| {
                        let state = Arc::clone(&state);
                        async move { handle_request(state, req, peer).await }
                    });
                    if let Err(err) = http1::Builder::new()
                        .serve_connection(io, service)
                        .with_upgrades()
                        .await
                    {
                        debug!(%peer, error = %err, "explicit proxy connection closed");
                    }
                });
            }
        }
    }
}

/// Run the local HTTP/HTTPS MITM proxy until shutdown.
///
/// Prefer [`run_explicit_proxy`] + [`run_transparent_proxy`] for enterprise deployments.
pub async fn run_proxy(
    listen: SocketAddr,
    gateway: Arc<GatewayClient>,
    ca_dir: PathBuf,
    shutdown: watch::Receiver<bool>,
) -> Result<(), ProxyError> {
    let state = build_proxy_state(gateway, ca_dir, Vec::new())?;
    run_explicit_proxy(listen, state, shutdown).await
}

async fn handle_request(
    state: Arc<ProxyState>,
    req: Request<hyper::body::Incoming>,
    peer: SocketAddr,
) -> Result<Response<Full<Bytes>>, Infallible> {
    let method = req.method().clone();
    let uri = req.uri().clone();

    // HTTPS MITM via CONNECT + hyper upgrade
    if method == Method::CONNECT {
        let authority = uri
            .authority()
            .map(|a| a.as_str())
            .unwrap_or("")
            .to_string();
        if state.should_mitm(&authority) {
            info!(%peer, host = %authority, "CONNECT to AI provider — starting MITM");
            mitm::spawn_connect_mitm(req, authority, Arc::clone(&state));
            return Ok(Response::builder()
                .status(StatusCode::OK)
                .body(Full::new(Bytes::new()))
                .unwrap());
        }
        info!(%peer, host = %authority, "CONNECT to non-MITM host — tunneling without inspection");
        spawn_connect_tunnel(req, authority);
        return Ok(Response::builder()
            .status(StatusCode::OK)
            .body(Full::new(Bytes::new()))
            .unwrap());
    }

    let host = req
        .headers()
        .get(hyper::header::HOST)
        .and_then(|v| v.to_str().ok())
        .unwrap_or("");

    if state.should_mitm(host) {
        info!(%peer, %host, %method, path = %uri.path(), "plain HTTP request intercepted");
        return Ok(handle_ai_request(state, req).await);
    }

    debug!(%peer, %host, "request not intercepted");
    Ok(forward_plain_request(state, req).await)
}

fn spawn_connect_tunnel(req: Request<hyper::body::Incoming>, authority: String) {
    tokio::spawn(async move {
        let upgraded = match hyper::upgrade::on(req).await {
            Ok(upgraded) => upgraded,
            Err(err) => {
                warn!(host = %authority, error = %err, "CONNECT tunnel upgrade failed");
                return;
            }
        };

        let mut client = TokioIo::new(upgraded);
        let mut upstream = match connect_marked(&authority, DEFAULT_SOCKET_MARK).await {
            Ok(stream) => stream,
            Err(err) => {
                warn!(host = %authority, error = %err, "CONNECT tunnel upstream failed");
                return;
            }
        };

        if let Err(err) = copy_bidirectional(&mut client, &mut upstream).await {
            debug!(host = %authority, error = %err, "CONNECT tunnel closed");
        }
    });
}

async fn handle_ai_request(
    state: Arc<ProxyState>,
    req: Request<hyper::body::Incoming>,
) -> Response<Full<Bytes>> {
    let host = req
        .headers()
        .get(hyper::header::HOST)
        .and_then(|v| v.to_str().ok())
        .unwrap_or("unknown")
        .to_string();

    let body_bytes = match req.into_body().collect().await {
        Ok(collected) => collected.to_bytes(),
        Err(err) => {
            warn!(error = %err, "failed to read intercepted request body");
            return proxy_status(StatusCode::BAD_REQUEST, "invalid request body");
        }
    };

    let provider = infer_provider(&host);
    let prompt = PromptRequest {
        provider: provider.clone(),
        model: "unknown".to_string(),
        messages: vec![serde_json::json!({
            "role": "user",
            "content": String::from_utf8_lossy(&body_bytes).to_string(),
        })],
        max_tokens: None,
        inspect_only: true,
    };

    match state.gateway.submit_prompt(&prompt).await {
        Ok(response) if response.decision == "blocked" => {
            let message = response
                .blocked_reason
                .unwrap_or_else(|| "Request blocked by AI-SPM policy".to_string());
            proxy_status(StatusCode::FORBIDDEN, &message)
        }
        Ok(response) => {
            let body = response
                .response_content
                .unwrap_or_else(|| format!("decision={}", response.decision));
            Response::builder()
                .status(StatusCode::OK)
                .header(hyper::header::CONTENT_TYPE, "application/json")
                .body(Full::new(Bytes::from(body)))
                .unwrap()
        }
        Err(err) => {
            warn!(error = %err, "gateway prompt submission failed");
            proxy_status(StatusCode::BAD_GATEWAY, &format!("gateway error: {err}"))
        }
    }
}

async fn forward_plain_request(
    state: Arc<ProxyState>,
    req: Request<hyper::body::Incoming>,
) -> Response<Full<Bytes>> {
    let (mut parts, body) = req.into_parts();
    let body_bytes = match body.collect().await {
        Ok(collected) => collected.to_bytes(),
        Err(err) => {
            warn!(error = %err, "failed to read proxied request body");
            return proxy_status(StatusCode::BAD_REQUEST, "invalid request body");
        }
    };

    if parts.uri.scheme().is_none() {
        let host = parts
            .headers
            .get(hyper::header::HOST)
            .and_then(|v| v.to_str().ok())
            .unwrap_or("");
        let path = parts
            .uri
            .path_and_query()
            .map(|p| p.as_str())
            .unwrap_or("/");
        let uri = format!("http://{host}{path}");
        match uri.parse::<Uri>() {
            Ok(uri) => parts.uri = uri,
            Err(err) => {
                warn!(%host, error = %err, "invalid proxied HTTP URI");
                return proxy_status(StatusCode::BAD_REQUEST, "invalid proxy request URI");
            }
        }
    }

    remove_hop_by_hop_headers(&mut parts.headers);
    let upstream_req = Request::from_parts(parts, Full::new(body_bytes));
    let upstream_res = match state.upstream.request(upstream_req).await {
        Ok(response) => response,
        Err(err) => {
            warn!(error = %err, "proxied HTTP request failed");
            return proxy_status(StatusCode::BAD_GATEWAY, "upstream request failed");
        }
    };

    let (parts, body) = upstream_res.into_parts();
    let body_bytes = match body.collect().await {
        Ok(collected) => collected.to_bytes(),
        Err(err) => {
            warn!(error = %err, "failed to read proxied response body");
            return proxy_status(StatusCode::BAD_GATEWAY, "upstream response failed");
        }
    };

    let mut response = Response::builder().status(parts.status);
    if let Some(headers) = response.headers_mut() {
        for (name, value) in parts.headers.iter() {
            if !is_hop_by_hop(name.as_str()) {
                headers.insert(name, value.clone());
            }
        }
    }

    response.body(Full::new(body_bytes)).unwrap()
}

/// Install the process-wide rustls crypto provider exactly once.
///
/// rustls 0.23 requires an explicit default provider when multiple backends
/// could be linked. Call this before any TLS (gateway client, MITM, local HTTPS).
/// Idempotent; a second call after one succeeds is a no-op.
pub fn ensure_crypto_provider() {
    use std::sync::Once;

    static INSTALL: Once = Once::new();
    INSTALL.call_once(|| {
        if rustls::crypto::ring::default_provider()
            .install_default()
            .is_err()
        {
            debug!("rustls crypto provider already installed");
        }
    });
}

/// AI API hosts MITM-inspected at the network layer (SDKs, IDE tools, server apps).
/// Consumer web UIs (ChatGPT/Claude/Gemini sites) use SPM-style mitmproxy instead —
/// Rust MITM of those hosts triggers Cloudflare Turnstile.
pub const DEFAULT_MITM_DOMAINS: &[&str] = &[
    "api.openai.com",
    "api.anthropic.com",
    "generativelanguage.googleapis.com",
    "api.x.ai",
    "api.cohere.ai",
    "api.mistral.ai",
    "api.groq.com",
    "api.perplexity.ai",
    "api.deepseek.com",
];

/// Cloudflare-protected web UIs — passthrough in the Rust agent so pages load.
/// Prompt masking for these is handled by mitmproxy (SPM-compatible path).
pub const CLOUDFLARE_PROTECTED_AI_DOMAINS: &[&str] = &[
    "chatgpt.com",
    "chat.openai.com",
    "ws.chatgpt.com",
    "ab.chatgpt.com",
    "claude.ai",
    "gemini.google.com",
];

#[derive(Debug, Error)]
pub enum ProxyError {
    #[error("proxy bind failed: {0}")]
    Bind(std::io::Error),
    #[error("proxy accept failed: {0}")]
    Accept(std::io::Error),
    #[error("MITM CA error: {0}")]
    Ca(#[from] ca::CaError),
    #[error("upstream client error: {0}")]
    Upstream(String),
}

pub struct ProxyState {
    pub gateway: Arc<GatewayClient>,
    pub ca: Arc<MitmCertificateAuthority>,
    pub upstream: upstream::HttpClient,
    pub mitm_domains: Vec<String>,
}

impl ProxyState {
    /// Network MITM for API hosts only. CF web UIs passthrough (masked via mitmproxy).
    pub fn should_mitm(&self, host: &str) -> bool {
        if host_matches_str(host, CLOUDFLARE_PROTECTED_AI_DOMAINS) {
            return false;
        }
        host_matches(host, &self.mitm_domains)
    }
}

fn infer_provider(host: &str) -> String {
    let host = host.to_ascii_lowercase();
    if host.contains("openai") || host.contains("chatgpt") {
        "openai".to_string()
    } else if host.contains("anthropic") || host.contains("claude") {
        "anthropic".to_string()
    } else if host.contains("gemini") || host.contains("generativelanguage") {
        "google".to_string()
    } else {
        "unknown".to_string()
    }
}

fn proxy_status(status: StatusCode, message: &str) -> Response<Full<Bytes>> {
    Response::builder()
        .status(status)
        .header(hyper::header::CONTENT_TYPE, "text/plain; charset=utf-8")
        .body(Full::new(Bytes::from(message.to_string())))
        .unwrap()
}

fn is_hop_by_hop(name: &str) -> bool {
    matches!(
        name.to_ascii_lowercase().as_str(),
        "connection"
            | "keep-alive"
            | "proxy-authenticate"
            | "proxy-authorization"
            | "te"
            | "trailers"
            | "transfer-encoding"
            | "upgrade"
            | "proxy-connection"
    )
}

fn remove_hop_by_hop_headers(headers: &mut hyper::HeaderMap) {
    for name in [
        "connection",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "te",
        "trailers",
        "transfer-encoding",
        "upgrade",
        "proxy-connection",
    ] {
        headers.remove(name);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn mitms_api_hosts_passthrough_web_uis() {
        assert!(should_intercept("api.openai.com"));
        assert!(should_intercept("api.anthropic.com"));
        assert!(!should_intercept("chatgpt.com"));
        assert!(!should_intercept("claude.ai"));
        assert!(!should_intercept("gemini.google.com"));
        assert!(!should_intercept("example.com"));
    }

    #[test]
    fn host_matching_handles_subdomains_and_ports() {
        let domains = vec!["api.openai.com".to_string()];
        assert!(host_matches("api.openai.com", &domains));
        assert!(host_matches("API.OpenAI.com:443", &domains));
        assert!(host_matches("eu.api.openai.com", &domains));
        assert!(!host_matches("notopenai.com", &domains));
    }
}
