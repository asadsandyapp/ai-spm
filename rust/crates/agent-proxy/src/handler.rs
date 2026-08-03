use std::sync::Arc;

use agent_core::config::{AgentConfig, OversizedAction};
use agent_core::policy::Action;
use agent_dlp::{highest_priority_action, mask_body, scan_body, Match, RuleSet};
use http::{header, Request, Response, StatusCode};
use http_body_util::BodyExt;
use hudsucker::{Body, HttpContext, HttpHandler, RequestOrResponse};

/// The proxy's `HttpHandler`: decides which hosts to intercept and runs the
/// DLP engine over the (buffered) bodies of intercepted requests.
#[derive(Clone)]
pub struct DlpHandler {
    config: Arc<AgentConfig>,
    ruleset: Arc<RuleSet>,
}

impl DlpHandler {
    pub fn new(config: Arc<AgentConfig>, ruleset: Arc<RuleSet>) -> Self {
        Self { config, ruleset }
    }
}

impl HttpHandler for DlpHandler {
    async fn should_intercept_connect(
        &mut self,
        _ctx: &HttpContext,
        req: &Request<Body>,
    ) -> bool {
        let host = req.uri().host().unwrap_or_default();
        let intercept = self.config.is_target_domain(host);
        if intercept {
            tracing::info!(host, "intercepting target domain");
        } else {
            tracing::debug!(host, "tunneling non-target domain");
        }
        intercept
    }

    async fn handle_request(&mut self, _ctx: &HttpContext, req: Request<Body>) -> RequestOrResponse {
        // WebSocket upgrade requests carry no scannable body; the actual
        // frame content is scanned later by `WsDlpHandler`. Strip
        // Sec-WebSocket-Extensions so the upstream server can't negotiate
        // permessage-deflate: hudsucker's WS client (tungstenite) has no
        // extension support, so compressed (RSV1-set) frames from a real
        // negotiated connection fail to parse ("Reserved bits are
        // non-zero"), breaking the tunnel outright. Dropping the offer
        // keeps both legs on plain, uncompressed frames.
        if is_websocket_upgrade(&req) {
            return RequestOrResponse::Request(strip_websocket_extensions(req));
        }

        let (parts, body) = req.into_parts();

        let host = request_host(&parts);
        let content_type = parts
            .headers
            .get(header::CONTENT_TYPE)
            .and_then(|v| v.to_str().ok())
            .map(str::to_owned);

        let collected = match body.collect().await {
            Ok(collected) => collected.to_bytes(),
            Err(err) => {
                // Forwarding upstream here would mean sending a request with
                // a body we know is truncated/corrupted (an empty body, not
                // "the real body, unread") — silently mutating what the
                // client sent. Fail the request back to the client instead
                // of risking the AI service receiving a broken request no
                // one asked it to process.
                tracing::warn!(host, %err, "failed to read request body, failing request");
                return RequestOrResponse::Response(body_read_failed_response());
            }
        };

        let max_body_bytes = self.config.proxy.max_body_bytes;
        if collected.len() > max_body_bytes {
            match self.config.proxy.on_oversized {
                OversizedAction::Block => {
                    tracing::warn!(
                        host,
                        len = collected.len(),
                        max = max_body_bytes,
                        "request body exceeds max_body_bytes, blocking (on_oversized=block)"
                    );
                    return RequestOrResponse::Response(oversized_block_response());
                }
                OversizedAction::Log => {
                    tracing::warn!(
                        host,
                        len = collected.len(),
                        max = max_body_bytes,
                        "request body exceeds max_body_bytes, passing through unscanned"
                    );
                    return RequestOrResponse::Request(Request::from_parts(parts, Body::from(collected)));
                }
            }
        }

        // Raw-traffic trace: opt-in only (RUST_LOG must enable `trace` for
        // agent_proxy), and separate from the "dlp match" log above, which
        // stays safe to run at `info` in production. This one dumps the
        // full body verbatim and must never be left on by default.
        tracing::trace!(
            host,
            method = %parts.method,
            uri = %parts.uri,
            headers = ?parts.headers,
            body = %String::from_utf8_lossy(&collected),
            "raw request"
        );

        let scan = scan_body(&self.ruleset, content_type.as_deref(), &collected);
        for m in &scan.matches {
            tracing::info!(
                host,
                rule_id = %m.rule_id,
                severity = ?m.severity,
                action = ?m.action,
                span_len = m.end - m.start,
                "dlp match"
            );
        }

        match highest_priority_action(&scan.matches) {
            Some(Action::Block) => {
                tracing::warn!(host, "blocking request");
                RequestOrResponse::Response(block_response(&scan.matches))
            }
            Some(Action::Mask) => {
                let (masked, _) = mask_body(&self.ruleset, content_type.as_deref(), &collected);
                let mut parts = parts;
                set_content_length(&mut parts.headers, masked.len());
                RequestOrResponse::Request(Request::from_parts(parts, Body::from(masked)))
            }
            Some(Action::Log) | None => {
                RequestOrResponse::Request(Request::from_parts(parts, Body::from(collected)))
            }
        }
    }
}

fn is_websocket_upgrade(req: &Request<Body>) -> bool {
    req.headers()
        .get(header::UPGRADE)
        .and_then(|v| v.to_str().ok())
        .is_some_and(|v| v.eq_ignore_ascii_case("websocket"))
}

fn strip_websocket_extensions(mut req: Request<Body>) -> Request<Body> {
    req.headers_mut().remove(header::SEC_WEBSOCKET_EXTENSIONS);
    req
}

fn request_host(parts: &http::request::Parts) -> String {
    parts
        .uri
        .host()
        .map(str::to_owned)
        .or_else(|| {
            parts
                .headers
                .get(header::HOST)
                .and_then(|v| v.to_str().ok())
                .map(str::to_owned)
        })
        .unwrap_or_default()
}

fn set_content_length(headers: &mut http::HeaderMap, len: usize) {
    if let Ok(value) = http::HeaderValue::from_str(&len.to_string()) {
        headers.insert(header::CONTENT_LENGTH, value);
    }
}

fn body_read_failed_response() -> Response<Body> {
    let body = serde_json::json!({
        "blocked_by": "AI-SPM DLP Agent",
        "message": "This request's body could not be read and was not forwarded.",
    });
    let bytes = serde_json::to_vec(&body).unwrap_or_default();

    Response::builder()
        .status(StatusCode::BAD_GATEWAY)
        .header(header::CONTENT_TYPE, "application/json")
        .body(Body::from(bytes))
        .expect("building a static response cannot fail")
}

fn oversized_block_response() -> Response<Body> {
    let body = serde_json::json!({
        "blocked_by": "AI-SPM DLP Agent",
        "message": "This request's body exceeds the configured size limit and was blocked \
                    (on_oversized = \"block\") rather than forwarded unscanned.",
    });
    let bytes = serde_json::to_vec(&body).unwrap_or_default();

    Response::builder()
        .status(StatusCode::FORBIDDEN)
        .header(header::CONTENT_TYPE, "application/json")
        .body(Body::from(bytes))
        .expect("building a static response cannot fail")
}

fn block_response(matches: &[Match]) -> Response<Body> {
    let rule_id = matches
        .iter()
        .find(|m| m.action == Action::Block)
        .map(|m| m.rule_id.clone())
        .unwrap_or_default();

    let body = serde_json::json!({
        "blocked_by": "AI-SPM DLP Agent",
        "rule": rule_id,
        "message": "This request was blocked because it appears to contain sensitive data. Contact IT if you believe this is an error.",
    });
    let bytes = serde_json::to_vec(&body).unwrap_or_default();

    Response::builder()
        .status(StatusCode::FORBIDDEN)
        .header(header::CONTENT_TYPE, "application/json")
        .body(Body::from(bytes))
        .expect("building a static response cannot fail")
}

#[cfg(test)]
mod tests {
    use super::*;

    fn upgrade_request(extensions: Option<&str>) -> Request<Body> {
        let mut builder = Request::builder()
            .method("GET")
            .uri("https://ws.chatgpt.com/p16/ws/user/abc")
            .header(header::UPGRADE, "websocket")
            .header(header::CONNECTION, "Upgrade");
        if let Some(ext) = extensions {
            builder = builder.header(header::SEC_WEBSOCKET_EXTENSIONS, ext);
        }
        builder.body(Body::empty()).unwrap()
    }

    #[test]
    fn detects_websocket_upgrade_request() {
        assert!(is_websocket_upgrade(&upgrade_request(None)));
    }

    #[test]
    fn plain_get_is_not_websocket_upgrade() {
        let req = Request::builder()
            .method("GET")
            .uri("https://chatgpt.com/backend-api/conversation")
            .body(Body::empty())
            .unwrap();
        assert!(!is_websocket_upgrade(&req));
    }

    #[test]
    fn strips_permessage_deflate_extension_on_upgrade() {
        let req = upgrade_request(Some("permessage-deflate; client_max_window_bits"));
        let stripped = strip_websocket_extensions(req);
        assert!(!stripped.headers().contains_key(header::SEC_WEBSOCKET_EXTENSIONS));
    }

    #[test]
    fn leaves_other_headers_alone_when_stripping_extensions() {
        let req = upgrade_request(Some("permessage-deflate"));
        let stripped = strip_websocket_extensions(req);
        assert_eq!(stripped.headers().get(header::UPGRADE).unwrap(), "websocket");
    }
}
