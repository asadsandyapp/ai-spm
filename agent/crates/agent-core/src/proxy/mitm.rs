//! HTTPS MITM: terminate TLS from the browser, inspect AI traffic, forward upstream.

use std::convert::Infallible;
use std::sync::Arc;

use bytes::Bytes;
use http_body_util::combinators::BoxBody;
use http_body_util::{BodyExt, Full};
use hyper::body::Incoming;
use hyper::header::HOST;
use hyper::service::service_fn;
use hyper::{Method, Request, Response, StatusCode, Uri};
use hyper_util::rt::{TokioExecutor, TokioIo};
use hyper_util::server::conn::auto::Builder as ServerBuilder;
use tokio_rustls::TlsAcceptor;
use tracing::{debug, info, warn};

use super::parser::{is_intercept_path, parse_request_body, rewrite_raw_body};
use super::upstream;
use super::ProxyState;
use crate::gateway::PromptRequest;

pub type BoxError = Box<dyn std::error::Error + Send + Sync + 'static>;
pub type HttpClient = upstream::HttpClient;

/// Streaming response body returned to the browser. Upstream response bodies are
/// forwarded as a stream (never fully buffered) so SSE/chunked AI responses and
/// Cloudflare challenge assets are not stalled.
type ResBody = BoxBody<Bytes, BoxError>;

/// Wrap fully-buffered bytes (block pages, error pages) in the streaming body type.
fn full_body(bytes: Bytes) -> ResBody {
    Full::new(bytes).map_err(|never| match never {}).boxed()
}

/// Spawn MITM on a transparently redirected TLS stream (no HTTP CONNECT).
pub fn spawn_transparent_mitm(
    stream: tokio::net::TcpStream,
    host: String,
    port: u16,
    state: Arc<ProxyState>,
) {
    tokio::spawn(async move {
        if let Err(err) = handle_transparent_tls(stream, &host, port, state).await {
            debug!(host = %host, error = %err, "transparent MITM session ended");
        }
    });
}

async fn handle_transparent_tls(
    stream: tokio::net::TcpStream,
    host: &str,
    port: u16,
    state: Arc<ProxyState>,
) -> Result<(), BoxError> {
    info!(%host, port, "TLS MITM starting on transparent redirected stream");

    let server_config = state
        .ca
        .server_config_for_host(host)
        .map_err(|e| -> BoxError { Box::new(e) })?;
    let acceptor = TlsAcceptor::from(server_config);
    let tls_stream = acceptor.accept(stream).await?;

    run_mitm_server(tls_stream, host.to_string(), port, state).await
}

/// Spawn MITM handling on a CONNECT-upgraded stream (must run in a tokio task).
pub fn spawn_connect_mitm(
    req: hyper::Request<Incoming>,
    authority: String,
    state: Arc<ProxyState>,
) {
    tokio::spawn(async move {
        let upgraded = match hyper::upgrade::on(req).await {
            Ok(upgraded) => upgraded,
            Err(err) => {
                warn!(host = %authority, error = %err, "CONNECT upgrade failed");
                return;
            }
        };
        if let Err(err) = handle_upgraded(upgraded, &authority, state).await {
            debug!(host = %authority, error = %err, "MITM session ended");
        }
    });
}

/// After hyper completes the CONNECT 200 upgrade, terminate TLS and inspect HTTP.
pub async fn handle_upgraded(
    upgraded: hyper::upgrade::Upgraded,
    authority: &str,
    state: Arc<ProxyState>,
) -> Result<(), String> {
    handle_upgraded_inner(upgraded, authority, state)
        .await
        .map_err(|e| e.to_string())
}

async fn handle_upgraded_inner(
    upgraded: hyper::upgrade::Upgraded,
    authority: &str,
    state: Arc<ProxyState>,
) -> Result<(), BoxError> {
    let (host, port) = parse_authority(authority)?;

    info!(%host, port, "TLS MITM starting on upgraded CONNECT stream");

    let server_config = state
        .ca
        .server_config_for_host(&host)
        .map_err(|e| -> BoxError { Box::new(e) })?;
    let acceptor = TlsAcceptor::from(server_config);
    let io = TokioIo::new(upgraded);
    let tls_stream = acceptor.accept(io).await?;

    run_mitm_server(tls_stream, host, port, state).await
}

async fn run_mitm_server<I>(
    io: I,
    host: String,
    port: u16,
    state: Arc<ProxyState>,
) -> Result<(), BoxError>
where
    I: tokio::io::AsyncRead + tokio::io::AsyncWrite + Unpin + Send + 'static,
{
    let io = TokioIo::new(io);
    let service = service_fn(move |req| {
        let state = Arc::clone(&state);
        let host = host.clone();
        async move {
            Ok::<Response<ResBody>, Infallible>(
                match handle_mitm_request(req, &host, port, state).await {
                    Ok(resp) => resp,
                    Err(err) => {
                        warn!(error = %err, "MITM request handler error");
                        proxy_error_response("Upstream request failed")
                    }
                },
            )
        }
    });

    ServerBuilder::new(TokioExecutor::new())
        .serve_connection(io, service)
        .await?;

    Ok(())
}

async fn handle_mitm_request(
    req: Request<Incoming>,
    host: &str,
    port: u16,
    state: Arc<ProxyState>,
) -> Result<Response<ResBody>, BoxError> {
    let method = req.method().clone();
    // Preserve the full path AND query string. Cloudflare's challenge platform
    // (`/cdn-cgi/challenge-platform/...?ray=...`) and provider APIs encode
    // required parameters in the query; dropping them breaks the challenge and
    // causes an infinite "Verifying…" loop.
    let path = req
        .uri()
        .path_and_query()
        .map(|pq| pq.as_str().to_string())
        .unwrap_or_else(|| req.uri().path().to_string());
    let headers = req.headers().clone();

    let body_bytes = req.into_body().collect().await?.to_bytes();
    let original_body = body_bytes.to_vec();

    let mut forward_body = original_body.clone();
    if method == Method::POST && is_intercept_path(&path) {
        if let Ok(body_str) = std::str::from_utf8(&original_body) {
            if let Some(parsed) = parse_request_body(host, body_str) {
                info!(
                    %host,
                    %path,
                    provider = %parsed.provider,
                    model = %parsed.model,
                    messages = parsed.messages.len(),
                    "intercepted AI prompt — submitting to security pipeline"
                );

                let gateway_messages: Vec<serde_json::Value> = parsed
                    .messages
                    .iter()
                    .map(|m| serde_json::json!({"role": m.role, "content": m.content}))
                    .collect();

                let prompt = PromptRequest {
                    provider: parsed.provider.clone(),
                    model: parsed.model.clone(),
                    messages: gateway_messages,
                    max_tokens: None,
                    inspect_only: true,
                };

                match state.gateway.submit_prompt(&prompt).await {
                    Ok(response) if response.decision == "blocked" => {
                        warn!(
                            block_code = ?response.block_code,
                            reason = ?response.blocked_reason,
                            "prompt blocked by AI-SPM policy"
                        );
                        let message = response
                            .blocked_reason
                            .unwrap_or_else(|| "Request blocked by AI-SPM security policy".into());
                        state
                            .status
                            .record_block(parsed.provider.clone(), message.clone());
                        return Ok(block_response(&message));
                    }
                    Ok(response) => {
                        if response.decision == "masked" {
                            if let Some(masked) = response.masked_messages {
                                if let Ok(body_str) = std::str::from_utf8(&original_body) {
                                    if let Some(rewritten) =
                                        rewrite_raw_body(body_str, &parsed.content_paths, &masked)
                                    {
                                        info!("PII masked in outbound request — forwarding sanitized body");
                                        forward_body = rewritten.into_bytes();
                                    }
                                }
                            }
                        } else {
                            debug!(decision = %response.decision, "prompt allowed — forwarding");
                        }
                    }
                    Err(err) => {
                        warn!(error = %err, "gateway inspection failed — forwarding unmodified");
                    }
                }
            }
        }
    }

    forward_request(
        host,
        port,
        method,
        &path,
        &headers,
        forward_body,
        &state.upstream,
    )
    .await
}

async fn forward_request(
    host: &str,
    port: u16,
    method: Method,
    path: &str,
    headers: &hyper::HeaderMap,
    body: Vec<u8>,
    client: &HttpClient,
) -> Result<Response<ResBody>, BoxError> {
    let uri: Uri = format!("https://{host}:{port}{path}")
        .parse()
        .map_err(|e| format!("invalid upstream URI: {e}"))?;

    let mut builder = Request::builder().method(method).uri(uri);
    {
        let req_headers = builder.headers_mut().unwrap();
        for (name, value) in headers.iter() {
            let name_str = name.as_str();
            // Skip hop-by-hop headers, the original Host, and content-length:
            // the body may have been rewritten (masked) to a different length,
            // so hyper must recompute content-length from the actual body.
            if is_hop_by_hop(name_str)
                || name_str.eq_ignore_ascii_case("host")
                || name_str.eq_ignore_ascii_case("content-length")
            {
                continue;
            }
            req_headers.insert(name, value.clone());
        }
        req_headers.insert(
            HOST,
            hyper::header::HeaderValue::from_str(host)
                .unwrap_or_else(|_| hyper::header::HeaderValue::from_static("localhost")),
        );
    }

    let upstream_req = builder.body(Full::new(Bytes::from(body)))?;
    let upstream_res = client.request(upstream_req).await?;

    let (parts, body) = upstream_res.into_parts();

    let mut response = Response::builder().status(parts.status);
    if let Some(resp_headers) = response.headers_mut() {
        for (name, value) in parts.headers.iter() {
            let name_str = name.as_str();
            // The upstream body is streamed through unbuffered; drop the original
            // content-length so hyper frames the streamed body correctly.
            // Strip alt-svc so the browser does not upgrade to HTTP/3 (QUIC), which
            // would bypass this HTTP proxy entirely.
            if is_hop_by_hop(name_str)
                || name_str.eq_ignore_ascii_case("content-length")
                || name_str.eq_ignore_ascii_case("alt-svc")
            {
                continue;
            }
            resp_headers.insert(name, value.clone());
        }
    }

    // Stream the response body straight to the browser. Buffering here would
    // stall Server-Sent Events (streamed AI responses) and large challenge
    // assets, which manifests as a hung page or a re-verification loop.
    let stream_body = body.map_err(|e| Box::new(e) as BoxError).boxed();
    Ok(response.body(stream_body)?)
}

fn block_response(message: &str) -> Response<ResBody> {
    let body = serde_json::json!({
        "detail": message,
        "blocked_by": "AI-SPM",
        "code": "POLICY_BLOCKED"
    });
    Response::builder()
        .status(StatusCode::FORBIDDEN)
        .header("content-type", "application/json")
        .body(full_body(Bytes::from(body.to_string())))
        .unwrap()
}

fn proxy_error_response(message: &str) -> Response<ResBody> {
    Response::builder()
        .status(StatusCode::BAD_GATEWAY)
        .header("content-type", "text/plain; charset=utf-8")
        .body(full_body(Bytes::from(message.to_string())))
        .unwrap()
}

fn parse_authority(authority: &str) -> Result<(String, u16), BoxError> {
    if let Some((host, port_str)) = authority.rsplit_once(':') {
        let port: u16 = port_str.parse().unwrap_or(443);
        Ok((host.to_string(), port))
    } else {
        Ok((authority.to_string(), 443))
    }
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
