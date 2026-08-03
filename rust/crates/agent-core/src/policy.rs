use std::path::Path;

use serde::Deserialize;

use crate::error::CoreError;

#[derive(Debug, Clone, Deserialize)]
pub struct PolicyDoc {
    #[serde(rename = "rule", default)]
    pub rules: Vec<RuleDef>,
}

#[derive(Debug, Clone, Deserialize)]
pub struct RuleDef {
    pub id: String,
    pub kind: RuleKind,
    pub pattern: String,
    pub severity: Severity,
    pub action: Action,
    /// Short type code used in the mask token (`[MASKED-<label>-NNN]`),
    /// e.g. `CNIC`, `CC`, `EMAIL`. Defaults to the upper-cased rule id.
    #[serde(default)]
    pub label: Option<String>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum RuleKind {
    Regex,
    Literal,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum Severity {
    Low,
    Medium,
    High,
    Critical,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum Action {
    Log,
    Mask,
    Block,
}

impl Action {
    /// Ordering used to pick the single action applied to a request when
    /// multiple rules match: block wins over mask wins over log.
    pub fn precedence(self) -> u8 {
        match self {
            Action::Log => 0,
            Action::Mask => 1,
            Action::Block => 2,
        }
    }
}

impl PolicyDoc {
    pub fn load(path: impl AsRef<Path>) -> Result<Self, CoreError> {
        let path = path.as_ref();
        let text = std::fs::read_to_string(path).map_err(|source| CoreError::Read {
            path: path.to_path_buf(),
            source,
        })?;
        toml::from_str(&text).map_err(|source| CoreError::Parse {
            path: path.to_path_buf(),
            source,
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_policy_doc() {
        let doc: PolicyDoc = toml::from_str(
            r#"
            [[rule]]
            id = "aws_access_key"
            kind = "regex"
            pattern = "AKIA[0-9A-Z]{16}"
            severity = "critical"
            action = "block"

            [[rule]]
            id = "codename_falcon"
            kind = "literal"
            pattern = "Project Falcon"
            severity = "medium"
            action = "log"
            "#,
        )
        .unwrap();

        assert_eq!(doc.rules.len(), 2);
        assert_eq!(doc.rules[0].id, "aws_access_key");
        assert_eq!(doc.rules[0].kind, RuleKind::Regex);
        assert_eq!(doc.rules[0].severity, Severity::Critical);
        assert_eq!(doc.rules[0].action, Action::Block);
    }

    #[test]
    fn action_precedence_orders_block_highest() {
        assert!(Action::Block.precedence() > Action::Mask.precedence());
        assert!(Action::Mask.precedence() > Action::Log.precedence());
    }
}
