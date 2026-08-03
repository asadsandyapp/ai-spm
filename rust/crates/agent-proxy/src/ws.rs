use std::sync::Arc;

use agent_core::config::{AgentConfig, OversizedAction};
use agent_core::policy::Action;
use agent_dlp::{highest_priority_action, mask_body, scan_body, RuleSet};
use hudsucker::tokio_tungstenite::tungstenite::Message;
use hudsucker::{WebSocketContext, WebSocketHandler};

/// The proxy's `WebSocketHandler`: runs the DLP engine over outbound
/// (client -> server) WebSocket frames on intercepted connections. Chat
/// clients (e.g. ChatGPT's web UI at `wss://ws.chatgpt.com`) carry real
/// conversation content over WebSockets, so the HTTP handler alone leaves
/// a bypass.
#[derive(Clone)]
pub struct WsDlpHandler {
    config: Arc<AgentConfig>,
    ruleset: Arc<RuleSet>,
}

impl WsDlpHandler {
    pub fn new(config: Arc<AgentConfig>, ruleset: Arc<RuleSet>) -> Self {
        Self { config, ruleset }
    }
}

impl WebSocketHandler for WsDlpHandler {
    async fn handle_message(
        &mut self,
        ctx: &WebSocketContext,
        message: Message,
    ) -> Option<Message> {
        // Only outbound frames carry data leaving the endpoint; inbound
        // (server -> client) frames pass through untouched.
        let host = match ctx {
            WebSocketContext::ClientToServer { dst, .. } => {
                dst.host().unwrap_or_default().to_owned()
            }
            WebSocketContext::ServerToClient { .. } => return Some(message),
        };

        // WebSocket interception only happens on connections the HTTP
        // handler chose to MITM, but the domain check is cheap and keeps
        // this handler safe if that ever changes.
        if !self.config.is_target_domain(&host) {
            return Some(message);
        }

        let max = self.config.proxy.max_body_bytes;
        match message {
            Message::Text(text) => {
                if text.len() > max {
                    return match self.config.proxy.on_oversized {
                        OversizedAction::Block => {
                            tracing::warn!(
                                host,
                                len = text.len(),
                                max,
                                "ws text frame exceeds max_body_bytes, dropping (on_oversized=block)"
                            );
                            None
                        }
                        OversizedAction::Log => {
                            tracing::warn!(
                                host,
                                len = text.len(),
                                max,
                                "ws text frame exceeds max_body_bytes, passing through unscanned"
                            );
                            Some(Message::Text(text))
                        }
                    };
                }

                // Raw-traffic trace: opt-in only, same rules as the HTTP
                // handler's raw-request trace — never on by default.
                tracing::trace!(host, frame = %text.as_str(), "raw ws text frame");

                match text_frame_verdict(&self.ruleset, &host, text.as_str()) {
                    FrameVerdict::Forward => Some(Message::Text(text)),
                    FrameVerdict::Masked(masked) => Some(Message::text(masked)),
                    FrameVerdict::Blocked => {
                        tracing::warn!(host, "blocking ws text frame");
                        None
                    }
                }
            }
            Message::Binary(data) => {
                if data.len() > max {
                    return match self.config.proxy.on_oversized {
                        OversizedAction::Block => {
                            tracing::warn!(
                                host,
                                len = data.len(),
                                max,
                                "ws binary frame exceeds max_body_bytes, dropping (on_oversized=block)"
                            );
                            None
                        }
                        OversizedAction::Log => {
                            tracing::warn!(
                                host,
                                len = data.len(),
                                max,
                                "ws binary frame exceeds max_body_bytes, passing through unscanned"
                            );
                            Some(Message::Binary(data))
                        }
                    };
                }

                match binary_frame_verdict(&self.ruleset, &host, &data) {
                    FrameVerdict::Forward => Some(Message::Binary(data)),
                    // binary_frame_verdict never masks; kept for exhaustiveness.
                    FrameVerdict::Masked(masked) => Some(Message::text(masked)),
                    FrameVerdict::Blocked => {
                        tracing::warn!(host, "blocking ws binary frame");
                        None
                    }
                }
            }
            // Control frames (ping/pong/close) carry no user payload worth
            // scanning; dropping them would break the connection.
            other => Some(other),
        }
    }
}

/// What to do with a single scanned frame.
#[derive(Debug, PartialEq, Eq)]
enum FrameVerdict {
    Forward,
    Masked(String),
    Blocked,
}

/// Scan an outbound text frame. WebSocket frames have no content type;
/// chat payloads are JSON in practice, and `scan_body`/`mask_body` fall
/// back to raw-text scanning when the frame doesn't parse as JSON.
fn text_frame_verdict(ruleset: &RuleSet, host: &str, text: &str) -> FrameVerdict {
    let scan = scan_body(ruleset, Some("application/json"), text.as_bytes());
    log_matches(host, "text", &scan.matches);

    match highest_priority_action(&scan.matches) {
        Some(Action::Block) => FrameVerdict::Blocked,
        Some(Action::Mask) => {
            let (masked, _) = mask_body(ruleset, Some("application/json"), text.as_bytes());
            FrameVerdict::Masked(String::from_utf8_lossy(&masked).into_owned())
        }
        Some(Action::Log) | None => FrameVerdict::Forward,
    }
}

/// Scan an outbound binary frame via lossy UTF-8 decoding. A masked
/// rewrite of an unknown binary encoding would corrupt the frame, so a
/// mask-action match downgrades to dropping the frame instead.
fn binary_frame_verdict(ruleset: &RuleSet, host: &str, data: &[u8]) -> FrameVerdict {
    let scan = scan_body(ruleset, None, data);
    log_matches(host, "binary", &scan.matches);

    match highest_priority_action(&scan.matches) {
        Some(Action::Block) => FrameVerdict::Blocked,
        Some(Action::Mask) => {
            tracing::warn!(host, "mask match in binary ws frame, dropping frame instead of rewriting");
            FrameVerdict::Blocked
        }
        Some(Action::Log) | None => FrameVerdict::Forward,
    }
}

fn log_matches(host: &str, frame_kind: &str, matches: &[agent_dlp::Match]) {
    for m in matches {
        tracing::info!(
            host,
            frame_kind,
            rule_id = %m.rule_id,
            severity = ?m.severity,
            action = ?m.action,
            span_len = m.end - m.start,
            "dlp match (websocket)"
        );
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use agent_core::policy::PolicyDoc;

    fn ruleset() -> RuleSet {
        let doc: PolicyDoc = toml::from_str(
            r#"
            [[rule]]
            id = "aws_access_key"
            kind = "regex"
            pattern = 'AKIA[0-9A-Z]{16}'
            severity = "critical"
            action = "block"

            [[rule]]
            id = "credit_card"
            kind = "regex"
            pattern = '\b\d{4}[ -]\d{4}[ -]\d{4}[ -]\d{1,4}\b'
            severity = "high"
            action = "mask"

            [[rule]]
            id = "codename_falcon"
            kind = "literal"
            pattern = "Project Falcon"
            severity = "medium"
            action = "log"
            "#,
        )
        .unwrap();
        RuleSet::compile(&doc).unwrap()
    }

    #[test]
    fn clean_text_frame_forwards() {
        let rs = ruleset();
        assert_eq!(
            text_frame_verdict(&rs, "ws.chatgpt.com", "just a normal message"),
            FrameVerdict::Forward
        );
    }

    #[test]
    fn log_match_forwards() {
        let rs = ruleset();
        assert_eq!(
            text_frame_verdict(&rs, "ws.chatgpt.com", "shipping project falcon"),
            FrameVerdict::Forward
        );
    }

    #[test]
    fn block_rule_blocks_text_frame() {
        let rs = ruleset();
        assert_eq!(
            text_frame_verdict(&rs, "ws.chatgpt.com", "key AKIAABCDEFGHIJKLMNOP"),
            FrameVerdict::Blocked
        );
    }

    #[test]
    fn mask_rule_masks_json_text_frame() {
        let rs = ruleset();
        let frame = r#"{"type":"message","data":{"content":"card 4111 1111 1111 1111 please"}}"#;
        match text_frame_verdict(&rs, "ws.chatgpt.com", frame) {
            FrameVerdict::Masked(masked) => {
                assert!(masked.contains("[MASKED-CREDIT_CARD-001]"));
                assert!(!masked.contains("4111 1111 1111 1111"));
                // Still valid JSON after the rewrite.
                serde_json::from_str::<serde_json::Value>(&masked).unwrap();
            }
            other => panic!("expected Masked, got {other:?}"),
        }
    }

    #[test]
    fn mask_rule_masks_non_json_text_frame() {
        let rs = ruleset();
        match text_frame_verdict(&rs, "ws.chatgpt.com", "card 4111 1111 1111 1111") {
            FrameVerdict::Masked(masked) => {
                assert_eq!(masked, "card [MASKED-CREDIT_CARD-001]");
            }
            other => panic!("expected Masked, got {other:?}"),
        }
    }

    #[test]
    fn binary_frame_with_block_match_blocks() {
        let rs = ruleset();
        assert_eq!(
            binary_frame_verdict(&rs, "ws.chatgpt.com", b"key AKIAABCDEFGHIJKLMNOP"),
            FrameVerdict::Blocked
        );
    }

    #[test]
    fn binary_frame_with_mask_match_blocks_instead_of_rewriting() {
        let rs = ruleset();
        assert_eq!(
            binary_frame_verdict(&rs, "ws.chatgpt.com", b"card 4111 1111 1111 1111"),
            FrameVerdict::Blocked
        );
    }

    #[test]
    fn clean_binary_frame_forwards() {
        let rs = ruleset();
        assert_eq!(
            binary_frame_verdict(&rs, "ws.chatgpt.com", &[0x01, 0x02, 0xff, 0xfe]),
            FrameVerdict::Forward
        );
    }
}
