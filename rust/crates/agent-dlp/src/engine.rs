use aho_corasick::AhoCorasick;
use agent_core::policy::{Action, PolicyDoc, RuleKind, Severity};
use regex::Regex;

#[derive(Debug, thiserror::Error)]
pub enum DlpError {
    #[error("rule '{id}' has an invalid regex pattern: {source}")]
    InvalidRegex {
        id: String,
        #[source]
        source: regex::Error,
    },
    #[error("failed to build literal matcher: {0}")]
    InvalidLiteralSet(#[from] aho_corasick::BuildError),
}

/// A single detection produced by scanning some text against a [`RuleSet`].
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Match {
    pub rule_id: String,
    /// Short type code for the mask token (e.g. `CNIC`, `CC`).
    pub label: String,
    pub severity: Severity,
    pub action: Action,
    pub start: usize,
    pub end: usize,
}

struct RegexRule {
    id: String,
    label: String,
    severity: Severity,
    action: Action,
    regex: Regex,
}

struct LiteralRule {
    id: String,
    label: String,
    severity: Severity,
    action: Action,
}

/// The mask-token type code for a rule: its explicit `label` if set,
/// otherwise the upper-cased rule id.
fn resolve_label(rule: &agent_core::policy::RuleDef) -> String {
    rule.label
        .clone()
        .unwrap_or_else(|| rule.id.to_uppercase())
}

/// Compiled set of DLP rules ready to scan text. Compilation is separated
/// from the policy document so scanning never touches the filesystem.
pub struct RuleSet {
    regex_rules: Vec<RegexRule>,
    literal_rules: Vec<LiteralRule>,
    literal_matcher: Option<AhoCorasick>,
}

impl RuleSet {
    pub fn compile(doc: &PolicyDoc) -> Result<Self, DlpError> {
        let mut regex_rules = Vec::new();
        let mut literal_rules = Vec::new();
        let mut literal_patterns = Vec::new();

        for rule in &doc.rules {
            match rule.kind {
                RuleKind::Regex => {
                    let regex =
                        Regex::new(&rule.pattern).map_err(|source| DlpError::InvalidRegex {
                            id: rule.id.clone(),
                            source,
                        })?;
                    regex_rules.push(RegexRule {
                        id: rule.id.clone(),
                        label: resolve_label(rule),
                        severity: rule.severity,
                        action: rule.action,
                        regex,
                    });
                }
                RuleKind::Literal => {
                    literal_patterns.push(rule.pattern.clone());
                    literal_rules.push(LiteralRule {
                        id: rule.id.clone(),
                        label: resolve_label(rule),
                        severity: rule.severity,
                        action: rule.action,
                    });
                }
            }
        }

        let literal_matcher = if literal_patterns.is_empty() {
            None
        } else {
            Some(
                AhoCorasick::builder()
                    .ascii_case_insensitive(true)
                    .build(&literal_patterns)?,
            )
        };

        Ok(Self {
            regex_rules,
            literal_rules,
            literal_matcher,
        })
    }

    /// Scan `text`, returning every match across all compiled rules. Matches
    /// are not deduplicated or sorted; callers that need a single action
    /// should reduce with [`highest_priority_action`].
    pub fn scan(&self, text: &str) -> Vec<Match> {
        let mut matches = Vec::new();

        for rule in &self.regex_rules {
            for m in rule.regex.find_iter(text) {
                matches.push(Match {
                    rule_id: rule.id.clone(),
                    label: rule.label.clone(),
                    severity: rule.severity,
                    action: rule.action,
                    start: m.start(),
                    end: m.end(),
                });
            }
        }

        if let Some(ac) = &self.literal_matcher {
            for m in ac.find_iter(text) {
                let rule = &self.literal_rules[m.pattern().as_usize()];
                matches.push(Match {
                    rule_id: rule.id.clone(),
                    label: rule.label.clone(),
                    severity: rule.severity,
                    action: rule.action,
                    start: m.start(),
                    end: m.end(),
                });
            }
        }

        matches
    }
}

/// Reduces a set of matches to the single action that should be applied to
/// the request: block beats mask beats log, ties broken by severity.
pub fn highest_priority_action(matches: &[Match]) -> Option<Action> {
    matches
        .iter()
        .max_by(|a, b| {
            a.action
                .precedence()
                .cmp(&b.action.precedence())
                .then(a.severity.cmp(&b.severity))
        })
        .map(|m| m.action)
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
            pattern = '\b(?:\d[ -]*?){13,16}\b'
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
    fn detects_aws_key() {
        let rs = ruleset();
        let matches = rs.scan("here is my key AKIAABCDEFGHIJKLMNOP in the message");
        assert_eq!(matches.len(), 1);
        assert_eq!(matches[0].rule_id, "aws_access_key");
        assert_eq!(matches[0].action, Action::Block);
    }

    #[test]
    fn detects_credit_card() {
        let rs = ruleset();
        let matches = rs.scan("card number 4111 1111 1111 1111 please charge it");
        assert!(matches.iter().any(|m| m.rule_id == "credit_card"));
    }

    #[test]
    fn detects_literal_case_insensitive() {
        let rs = ruleset();
        let matches = rs.scan("we are shipping project falcon next week");
        assert_eq!(matches.len(), 1);
        assert_eq!(matches[0].rule_id, "codename_falcon");
        assert_eq!(matches[0].action, Action::Log);
    }

    #[test]
    fn clean_text_has_no_matches() {
        let rs = ruleset();
        assert!(rs.scan("just a normal chat message, nothing sensitive here").is_empty());
    }

    #[test]
    fn block_wins_over_mask_and_log() {
        let rs = ruleset();
        let matches = rs.scan("key AKIAABCDEFGHIJKLMNOP and project falcon and card 4111 1111 1111 1111");
        assert_eq!(highest_priority_action(&matches), Some(Action::Block));
    }

    #[test]
    fn mask_wins_over_log_when_no_block() {
        let rs = ruleset();
        let matches = rs.scan("project falcon uses card 4111 1111 1111 1111");
        assert_eq!(highest_priority_action(&matches), Some(Action::Mask));
    }
}
