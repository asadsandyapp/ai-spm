//! Parse AI provider request bodies (ChatGPT web UI, OpenAI API, Anthropic).

use serde_json::{json, Value};

/// A user/assistant message extracted from a provider-specific JSON body.
#[derive(Debug, Clone)]
pub struct ExtractedMessage {
    pub role: String,
    pub content: String,
}

/// Result of parsing an intercepted request body.
#[derive(Debug)]
pub struct ParsedAiRequest {
    pub provider: String,
    pub model: String,
    pub messages: Vec<ExtractedMessage>,
    /// JSON pointer-like paths to each message's text content for rewriting.
    pub content_paths: Vec<ContentPath>,
}

/// Describes where message text lives inside the original JSON for in-place rewriting.
#[derive(Debug, Clone)]
pub enum ContentPath {
    /// OpenAI API / Anthropic messages: messages[i].content (string)
    OpenAiMessage { index: usize },
    /// ChatGPT web: messages[i].content.parts[j]
    ChatGptPart { msg_index: usize, part_index: usize },
    /// Anthropic API (api.anthropic.com /v1/messages): messages[i].content[j].text
    AnthropicBlock { msg_index: usize, block_index: usize },
    /// Gemini API (generateContent): contents[i].parts[j].text
    GeminiPart { content_index: usize, part_index: usize },
    /// Claude web UI (claude.ai completion): top-level "prompt" string
    ClaudePrompt,
}

/// Returns true when this HTTP path carries user prompt content worth inspecting.
pub fn is_intercept_path(path: &str) -> bool {
    let path = path.split('?').next().unwrap_or(path);
    let lower = path.to_ascii_lowercase();
    // OpenAI / ChatGPT
    path.ends_with("/conversation")
        || path.ends_with("/chat/completions")
        || path.ends_with("/completions")
        || path.contains("/backend-api/conversation")
        || path.contains("/backend-anon/conversation")
        // Anthropic API + Claude web UI
        || path.ends_with("/v1/messages")
        || path.ends_with("/v1/complete")
        || path.ends_with("/completion")
        || path.ends_with("/retry_completion")
        // Google Gemini API (generateContent / streamGenerateContent)
        || lower.contains("generatecontent")
}

/// Extract messages from a JSON request body across all supported providers.
///
/// Handles: OpenAI chat completions, ChatGPT web UI conversations, Anthropic
/// `/v1/messages` (string or text-block content), Claude web UI completions
/// (top-level `prompt`), and Google Gemini `generateContent` (`contents`).
pub fn parse_request_body(host: &str, body: &str) -> Option<ParsedAiRequest> {
    let root: Value = serde_json::from_str(body).ok()?;
    let provider = infer_provider(host);

    // Google Gemini: {"contents":[{"role":"user","parts":[{"text":"..."}]}]}
    if let Some(contents) = root.get("contents").and_then(|c| c.as_array()) {
        let mut extracted = Vec::new();
        let mut paths = Vec::new();
        for (content_index, item) in contents.iter().enumerate() {
            let role = item
                .get("role")
                .and_then(|r| r.as_str())
                .unwrap_or("user")
                .to_string();
            if let Some(parts) = item.get("parts").and_then(|p| p.as_array()) {
                for (part_index, part) in parts.iter().enumerate() {
                    if let Some(text) = part.get("text").and_then(|t| t.as_str()) {
                        if !text.is_empty() {
                            extracted.push(ExtractedMessage {
                                role: role.clone(),
                                content: text.to_string(),
                            });
                            paths.push(ContentPath::GeminiPart {
                                content_index,
                                part_index,
                            });
                        }
                    }
                }
            }
        }
        if !extracted.is_empty() {
            let model = root
                .get("model")
                .and_then(|m| m.as_str())
                .unwrap_or("gemini")
                .to_string();
            return Some(ParsedAiRequest {
                provider,
                model,
                messages: extracted,
                content_paths: paths,
            });
        }
    }

    // Chat "messages" array: OpenAI, Anthropic /v1/messages, and ChatGPT web UI.
    // A single pass handles string content, ChatGPT content.parts, and Anthropic
    // content[] text blocks so mixed message shapes are all inspected in order.
    if let Some(messages) = root.get("messages").and_then(|m| m.as_array()) {
        let mut extracted = Vec::new();
        let mut paths = Vec::new();
        for (msg_index, msg) in messages.iter().enumerate() {
            let role = msg
                .pointer("/author/role")
                .or_else(|| msg.get("role"))
                .and_then(|r| r.as_str())
                .unwrap_or("user")
                .to_string();

            let Some(content) = msg.get("content") else {
                continue;
            };

            // a) Plain string content (OpenAI, Anthropic simple, ChatGPT web alt)
            if let Some(text) = content.as_str() {
                if !text.is_empty() {
                    extracted.push(ExtractedMessage {
                        role: role.clone(),
                        content: text.to_string(),
                    });
                    paths.push(ContentPath::OpenAiMessage { index: msg_index });
                }
                continue;
            }

            // b) ChatGPT web UI: content.parts = ["..."]
            if let Some(parts) = content.get("parts").and_then(|p| p.as_array()) {
                for (part_index, part) in parts.iter().enumerate() {
                    if let Some(text) = part.as_str() {
                        if !text.is_empty() {
                            extracted.push(ExtractedMessage {
                                role: role.clone(),
                                content: text.to_string(),
                            });
                            paths.push(ContentPath::ChatGptPart {
                                msg_index,
                                part_index,
                            });
                        }
                    }
                }
                continue;
            }

            // c) Anthropic API: content = [{"type":"text","text":"..."}, ...]
            if let Some(blocks) = content.as_array() {
                for (block_index, block) in blocks.iter().enumerate() {
                    if block.get("type").and_then(|t| t.as_str()) != Some("text") {
                        continue;
                    }
                    if let Some(text) = block.get("text").and_then(|t| t.as_str()) {
                        if !text.is_empty() {
                            extracted.push(ExtractedMessage {
                                role: role.clone(),
                                content: text.to_string(),
                            });
                            paths.push(ContentPath::AnthropicBlock {
                                msg_index,
                                block_index,
                            });
                        }
                    }
                }
                continue;
            }
        }
        if !extracted.is_empty() {
            let model = root
                .get("model")
                .and_then(|m| m.as_str())
                .unwrap_or("unknown")
                .to_string();
            return Some(ParsedAiRequest {
                provider,
                model,
                messages: extracted,
                content_paths: paths,
            });
        }
    }

    // Claude web UI (claude.ai): {"prompt":"...", "parent_message_uuid":"...", ...}
    if let Some(text) = root.get("prompt").and_then(|p| p.as_str()) {
        if !text.is_empty() {
            let model = root
                .get("model")
                .and_then(|m| m.as_str())
                .unwrap_or("claude")
                .to_string();
            return Some(ParsedAiRequest {
                provider,
                model,
                messages: vec![ExtractedMessage {
                    role: "user".to_string(),
                    content: text.to_string(),
                }],
                content_paths: vec![ContentPath::ClaudePrompt],
            });
        }
    }

    None
}

/// Rewrite message content in the original JSON body using masked text from the gateway.
pub fn rewrite_body_with_masked(
    mut root: Value,
    paths: &[ContentPath],
    masked_messages: &[serde_json::Value],
) -> Option<String> {
    for (path, masked) in paths.iter().zip(masked_messages.iter()) {
        let new_content = masked.get("content").and_then(|c| c.as_str())?;
        match path {
            ContentPath::OpenAiMessage { index } => {
                if let Some(msg) = root
                    .get_mut("messages")
                    .and_then(|m| m.as_array_mut())
                    .and_then(|arr| arr.get_mut(*index))
                {
                    msg["content"] = json!(new_content);
                }
            }
            ContentPath::ChatGptPart {
                msg_index,
                part_index,
            } => {
                if let Some(part) = root
                    .get_mut("messages")
                    .and_then(|m| m.as_array_mut())
                    .and_then(|arr| arr.get_mut(*msg_index))
                    .and_then(|msg| msg.get_mut("content"))
                    .and_then(|c| c.get_mut("parts"))
                    .and_then(|p| p.as_array_mut())
                    .and_then(|arr| arr.get_mut(*part_index))
                {
                    *part = json!(new_content);
                }
            }
            ContentPath::AnthropicBlock {
                msg_index,
                block_index,
            } => {
                if let Some(block) = root
                    .get_mut("messages")
                    .and_then(|m| m.as_array_mut())
                    .and_then(|arr| arr.get_mut(*msg_index))
                    .and_then(|msg| msg.get_mut("content"))
                    .and_then(|c| c.as_array_mut())
                    .and_then(|arr| arr.get_mut(*block_index))
                {
                    block["text"] = json!(new_content);
                }
            }
            ContentPath::GeminiPart {
                content_index,
                part_index,
            } => {
                if let Some(part) = root
                    .get_mut("contents")
                    .and_then(|c| c.as_array_mut())
                    .and_then(|arr| arr.get_mut(*content_index))
                    .and_then(|item| item.get_mut("parts"))
                    .and_then(|p| p.as_array_mut())
                    .and_then(|arr| arr.get_mut(*part_index))
                {
                    part["text"] = json!(new_content);
                }
            }
            ContentPath::ClaudePrompt => {
                if let Some(prompt) = root.get_mut("prompt") {
                    *prompt = json!(new_content);
                }
            }
        }
    }
    serde_json::to_string(&root).ok()
}

fn infer_provider(host: &str) -> String {
    let host = host.to_ascii_lowercase();
    if host.contains("openai") || host.contains("chatgpt") {
        "openai".to_string()
    } else if host.contains("anthropic") || host.contains("claude") {
        "anthropic".to_string()
    } else if host.contains("gemini")
        || host.contains("generativelanguage")
        || host.contains("google")
    {
        "google".to_string()
    } else {
        "unknown".to_string()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_openai_chat_completions() {
        let body = r#"{"model":"gpt-4o","messages":[{"role":"user","content":"hello world"}]}"#;
        let parsed = parse_request_body("api.openai.com", body).unwrap();
        assert_eq!(parsed.provider, "openai");
        assert_eq!(parsed.messages.len(), 1);
        assert_eq!(parsed.messages[0].content, "hello world");
    }

    #[test]
    fn parses_chatgpt_conversation() {
        let body = r#"{"model":"gpt-4o","messages":[{"id":"1","author":{"role":"user"},"content":{"content_type":"text","parts":["my email is test@example.com"]}}]}"#;
        let parsed = parse_request_body("chat.openai.com", body).unwrap();
        assert_eq!(parsed.messages.len(), 1);
        assert!(parsed.messages[0].content.contains("test@example.com"));
    }

    #[test]
    fn rewrites_openai_body() {
        let body =
            r#"{"model":"gpt-4o","messages":[{"role":"user","content":"secret@email.com"}]}"#;
        let parsed = parse_request_body("api.openai.com", body).unwrap();
        let root: Value = serde_json::from_str(body).unwrap();
        let masked = vec![json!({"role":"user","content":"***@***.com"})];
        let out = rewrite_body_with_masked(root, &parsed.content_paths, &masked).unwrap();
        assert!(out.contains("***@***.com"));
        assert!(!out.contains("secret@email.com"));
    }

    #[test]
    fn parses_and_rewrites_claude_web_prompt() {
        let body = r#"{"prompt":"my email is test@example.com","parent_message_uuid":"abc","rendering_mode":"messages"}"#;
        let parsed = parse_request_body("claude.ai", body).unwrap();
        assert_eq!(parsed.provider, "anthropic");
        assert_eq!(parsed.messages.len(), 1);
        assert!(parsed.messages[0].content.contains("test@example.com"));

        let root: Value = serde_json::from_str(body).unwrap();
        let masked = vec![json!({"role":"user","content":"my email is ***@***.com"})];
        let out = rewrite_body_with_masked(root, &parsed.content_paths, &masked).unwrap();
        assert!(out.contains("***@***.com"));
        assert!(!out.contains("test@example.com"));
        // Unrelated fields survive the rewrite.
        assert!(out.contains("parent_message_uuid"));
    }

    #[test]
    fn parses_and_rewrites_anthropic_messages_blocks() {
        let body = r#"{"model":"claude-3-5-sonnet","messages":[{"role":"user","content":[{"type":"text","text":"call me at 415-555-0100"}]}]}"#;
        let parsed = parse_request_body("api.anthropic.com", body).unwrap();
        assert_eq!(parsed.provider, "anthropic");
        assert_eq!(parsed.messages.len(), 1);
        assert!(parsed.messages[0].content.contains("415-555-0100"));

        let root: Value = serde_json::from_str(body).unwrap();
        let masked = vec![json!({"role":"user","content":"call me at ***-***-****"})];
        let out = rewrite_body_with_masked(root, &parsed.content_paths, &masked).unwrap();
        assert!(out.contains("***-***-****"));
        assert!(!out.contains("415-555-0100"));
        // Block structure preserved.
        assert!(out.contains("\"type\":\"text\""));
    }

    #[test]
    fn parses_and_rewrites_gemini_contents() {
        let body = r#"{"contents":[{"role":"user","parts":[{"text":"SSN 123-45-6789"}]}]}"#;
        let parsed = parse_request_body("generativelanguage.googleapis.com", body).unwrap();
        assert_eq!(parsed.provider, "google");
        assert_eq!(parsed.messages.len(), 1);
        assert!(parsed.messages[0].content.contains("123-45-6789"));

        let root: Value = serde_json::from_str(body).unwrap();
        let masked = vec![json!({"role":"user","content":"SSN ***-**-****"})];
        let out = rewrite_body_with_masked(root, &parsed.content_paths, &masked).unwrap();
        assert!(out.contains("***-**-****"));
        assert!(!out.contains("123-45-6789"));
    }

    #[test]
    fn intercepts_multi_provider_paths() {
        assert!(is_intercept_path("/v1/messages"));
        assert!(is_intercept_path(
            "/api/organizations/x/chat_conversations/y/completion"
        ));
        assert!(is_intercept_path(
            "/v1beta/models/gemini-1.5-pro:generateContent?key=abc"
        ));
        assert!(is_intercept_path(
            "/v1beta/models/gemini-1.5-pro:streamGenerateContent"
        ));
        assert!(!is_intercept_path("/static/app.js"));
    }
}
