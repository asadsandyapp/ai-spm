use serde_json::Value;

use crate::engine::{Match, RuleSet};

/// Result of scanning (and optionally masking) a request body.
pub struct BodyScan {
    /// All matches found across every string leaf (JSON) or the raw text
    /// (non-JSON). Byte spans are relative to the leaf/text they were found
    /// in, not the original body — callers must not assume they index into
    /// `body`.
    pub matches: Vec<Match>,
}

/// Scan `body` for DLP matches without mutating it. If `content_type`
/// indicates JSON, only string leaf values are scanned (chat payloads are
/// overwhelmingly string-valued at the leaves); otherwise the raw text is
/// scanned directly.
pub fn scan_body(ruleset: &RuleSet, content_type: Option<&str>, body: &[u8]) -> BodyScan {
    if is_json(content_type) {
        if let Ok(value) = serde_json::from_slice::<Value>(body) {
            let mut matches = Vec::new();
            scan_json_leaves(ruleset, &value, &mut matches);
            return BodyScan { matches };
        }
    }

    let text = String::from_utf8_lossy(body);
    BodyScan {
        matches: ruleset.scan(&text),
    }
}

/// Scan `body` and return a masked copy with every matched span in string
/// leaves replaced by `[MASKED-<label>-NNN]` (see [`redact_spans`]), plus the
/// matches that were found (for logging). Falls back to masking raw text
/// directly when the body isn't valid JSON.
pub fn mask_body(ruleset: &RuleSet, content_type: Option<&str>, body: &[u8]) -> (Vec<u8>, Vec<Match>) {
    // One counter per message: mask tokens are numbered [MASKED-<label>-001],
    // -002, ... in the order spans are redacted, restarting for each body/frame.
    let mut counter = 0usize;

    if is_json(content_type) {
        if let Ok(mut value) = serde_json::from_slice::<Value>(body) {
            let mut matches = Vec::new();
            mask_json_leaves(ruleset, &mut value, &mut matches, &mut counter);
            let masked = serde_json::to_vec(&value).expect("re-serializing a parsed Value cannot fail");
            return (masked, matches);
        }
    }

    let text = String::from_utf8_lossy(body);
    let matches = ruleset.scan(&text);
    let masked = redact_spans(&text, &matches, &mut counter);
    (masked.into_bytes(), matches)
}

fn is_json(content_type: Option<&str>) -> bool {
    content_type
        .map(|ct| ct.to_ascii_lowercase().contains("application/json"))
        .unwrap_or(false)
}

fn scan_json_leaves(ruleset: &RuleSet, value: &Value, matches: &mut Vec<Match>) {
    match value {
        Value::String(s) => matches.extend(ruleset.scan(s)),
        Value::Array(items) => {
            for item in items {
                scan_json_leaves(ruleset, item, matches);
            }
        }
        Value::Object(map) => {
            for v in map.values() {
                scan_json_leaves(ruleset, v, matches);
            }
        }
        _ => {}
    }
}

fn mask_json_leaves(ruleset: &RuleSet, value: &mut Value, matches: &mut Vec<Match>, counter: &mut usize) {
    match value {
        Value::String(s) => {
            let leaf_matches = ruleset.scan(s);
            if !leaf_matches.is_empty() {
                *s = redact_spans(s, &leaf_matches, counter);
                matches.extend(leaf_matches);
            }
        }
        Value::Array(items) => {
            for item in items {
                mask_json_leaves(ruleset, item, matches, counter);
            }
        }
        Value::Object(map) => {
            for v in map.values_mut() {
                mask_json_leaves(ruleset, v, matches, counter);
            }
        }
        _ => {}
    }
}

/// Replace every matched span in `text` with `[MASKED-<label>-NNN]`, where
/// NNN is a zero-padded per-message sequence number taken from `counter`
/// (incremented for each span redacted). Overlapping matches are resolved by
/// keeping the first (leftmost) one encountered after sorting by start offset.
fn redact_spans(text: &str, matches: &[Match], counter: &mut usize) -> String {
    if matches.is_empty() {
        return text.to_string();
    }

    let mut sorted: Vec<&Match> = matches.iter().collect();
    sorted.sort_by_key(|m| m.start);

    let mut out = String::with_capacity(text.len());
    let mut cursor = 0usize;

    for m in sorted {
        if m.start < cursor {
            // Overlaps a span we already redacted; skip it.
            continue;
        }
        *counter += 1;
        out.push_str(&text[cursor..m.start]);
        out.push_str(&format!("[MASKED-{}-{:03}]", m.label, counter));
        cursor = m.end;
    }
    out.push_str(&text[cursor..]);
    out
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
            label = "CC"
            pattern = '\b\d{4}[ -]\d{4}[ -]\d{4}[ -]\d{1,4}\b'
            severity = "high"
            action = "mask"
            "#,
        )
        .unwrap();
        RuleSet::compile(&doc).unwrap()
    }

    #[test]
    fn masks_json_string_leaf() {
        let rs = ruleset();
        let body = br#"{"messages":[{"role":"user","content":"card 4111 1111 1111 1111 please"}]}"#;
        let (masked, matches) = mask_body(&rs, Some("application/json"), body);
        assert_eq!(matches.len(), 1);
        let masked_str = String::from_utf8(masked).unwrap();
        assert!(masked_str.contains("[MASKED-CC-001]"));
        assert!(!masked_str.contains("4111 1111 1111 1111"));
    }

    #[test]
    fn scan_does_not_mutate() {
        let rs = ruleset();
        let body = br#"{"content":"key AKIAABCDEFGHIJKLMNOP"}"#;
        let scan = scan_body(&rs, Some("application/json"), body);
        assert_eq!(scan.matches.len(), 1);
        assert_eq!(scan.matches[0].rule_id, "aws_access_key");
    }

    #[test]
    fn masks_raw_text_when_not_json() {
        let rs = ruleset();
        let body = b"card 4111 1111 1111 1111";
        let (masked, matches) = mask_body(&rs, Some("text/plain"), body);
        assert_eq!(matches.len(), 1);
        assert_eq!(
            String::from_utf8(masked).unwrap(),
            "card [MASKED-CC-001]"
        );
    }

    #[test]
    fn counter_increments_per_message_across_leaves() {
        let rs = ruleset();
        let body = br#"{"a":"card 4111 1111 1111 1111","b":"card 4222 2222 2222 2222"}"#;
        let (masked, matches) = mask_body(&rs, Some("application/json"), body);
        assert_eq!(matches.len(), 2);
        let masked_str = String::from_utf8(masked).unwrap();
        // Two distinct sequence numbers within the one message.
        assert!(masked_str.contains("[MASKED-CC-001]"));
        assert!(masked_str.contains("[MASKED-CC-002]"));
    }
}
