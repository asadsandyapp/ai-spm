use std::path::{Path, PathBuf};

use serde::Deserialize;
use uuid::Uuid;

use crate::error::CoreError;

#[derive(Debug, Clone, Deserialize)]
pub struct AgentConfig {
    pub proxy: ProxyConfig,
    pub ca: CaConfig,
    pub targets: TargetsConfig,
    pub policy: PolicyConfig,
    #[serde(default)]
    pub logging: LoggingConfig,
    #[serde(default)]
    pub sysnet: SysnetConfig,
    #[serde(default)]
    pub cloud: CloudConfig,
}

#[derive(Debug, Clone, Deserialize)]
pub struct ProxyConfig {
    pub listen_addr: String,
    pub listen_port: u16,
    #[serde(default = "default_max_body_bytes")]
    pub max_body_bytes: usize,
    #[serde(default)]
    pub on_oversized: OversizedAction,
}

fn default_max_body_bytes() -> usize {
    10 * 1024 * 1024
}

#[derive(Debug, Clone, Copy, Default, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum OversizedAction {
    #[default]
    Log,
    Block,
}

#[derive(Debug, Clone, Deserialize)]
pub struct CaConfig {
    pub cert_path: PathBuf,
    pub key_path: PathBuf,
}

#[derive(Debug, Clone, Deserialize)]
pub struct TargetsConfig {
    pub domains: Vec<String>,
}

#[derive(Debug, Clone, Deserialize)]
pub struct PolicyConfig {
    pub source: PathBuf,
}

#[derive(Debug, Clone, Deserialize)]
pub struct LoggingConfig {
    #[serde(default = "default_log_level")]
    pub level: String,
    /// Directory for the daily-rotating log file. Relative paths are
    /// resolved against the current working directory `agentd` is started
    /// from.
    #[serde(default = "default_log_dir")]
    pub file_dir: PathBuf,
}

impl Default for LoggingConfig {
    fn default() -> Self {
        Self {
            level: default_log_level(),
            file_dir: default_log_dir(),
        }
    }
}

fn default_log_level() -> String {
    "info".to_string()
}

fn default_log_dir() -> PathBuf {
    PathBuf::from("logs")
}

#[derive(Debug, Clone, Deserialize)]
pub struct SysnetConfig {
    /// Where to write the generated PAC (Proxy Auto-Config) file used to
    /// scope the current user's browser traffic to only the configured
    /// target domains.
    #[serde(default = "default_pac_path")]
    pub pac_path: PathBuf,
    /// Loopback port `agentd` serves the PAC file on over HTTP. The proxy
    /// auto-config URL points here (`http://<listen_addr>:<pac_port>/proxy.pac`).
    /// HTTP is required because Chromium browsers refuse to load a PAC from a
    /// `file://` URL.
    #[serde(default = "default_pac_port")]
    pub pac_port: u16,
}

impl Default for SysnetConfig {
    fn default() -> Self {
        Self {
            pac_path: default_pac_path(),
            pac_port: default_pac_port(),
        }
    }
}

fn default_pac_path() -> PathBuf {
    PathBuf::from("data/proxy.pac")
}

fn default_pac_port() -> u16 {
    8444
}

/// Cloud/fleet registration - opt-in. An agent with no `[cloud]` section (or
/// with either field blank) stays fully standalone: nothing here is read
/// unless both fields are set, so existing local-only deployments are
/// unaffected.
#[derive(Debug, Clone, Default, Deserialize)]
pub struct CloudConfig {
    /// Base URL of the AI-SPM control-plane gateway, e.g.
    /// `https://gateway.example.com` (no trailing slash).
    #[serde(default)]
    pub gateway_url: Option<String>,
    /// The company's install token, as distributed by an admin: a single
    /// opaque string shaped `<org_id-uuid>.<secret>` - see
    /// [`CloudConfig::parse_install_token`] for why it's one field instead of
    /// two.
    #[serde(default)]
    pub install_token: Option<String>,
    /// Where registration state (`registration.json`) and the issued mTLS
    /// material (`agent.crt`/`agent.key`/`ca.crt`) are persisted. Resolved
    /// against the config file's own directory by [`AgentConfig::load`],
    /// same as `ca.cert_path`/`policy.source` etc.
    #[serde(default = "default_cloud_state_dir")]
    pub state_dir: PathBuf,
}

fn default_cloud_state_dir() -> PathBuf {
    PathBuf::from("data/cloud")
}

impl CloudConfig {
    /// True once both `gateway_url` and `install_token` are set - the signal
    /// to attempt registration at all.
    pub fn is_configured(&self) -> bool {
        self.gateway_url.as_deref().is_some_and(|s| !s.is_empty())
            && self.install_token.as_deref().is_some_and(|s| !s.is_empty())
    }

    /// Split `install_token` into the `org_id` the backend's `X-Org-ID`
    /// header needs and the `org_token` secret it validates against - one
    /// token for an admin to distribute/paste, split locally so the wire
    /// contract (which needs both pieces separately) doesn't leak into the
    /// install UX.
    pub fn parse_install_token(&self) -> Result<(Uuid, String), CoreError> {
        let token = self
            .install_token
            .as_deref()
            .ok_or(CoreError::InvalidInstallToken {
                reason: "install_token is not set".to_string(),
            })?;

        let (org_id, secret) = token.split_once('.').ok_or(CoreError::InvalidInstallToken {
            reason: "expected \"<org_id>.<secret>\", no '.' separator found".to_string(),
        })?;

        let org_id = Uuid::parse_str(org_id).map_err(|source| CoreError::InvalidInstallToken {
            reason: format!("{org_id:?} is not a valid org_id UUID: {source}"),
        })?;

        if secret.len() < 32 {
            return Err(CoreError::InvalidInstallToken {
                reason: format!(
                    "secret portion is {} chars, expected at least 32",
                    secret.len()
                ),
            });
        }

        Ok((org_id, secret.to_string()))
    }
}

impl AgentConfig {
    /// Load and parse `path`, then resolve every path field it contains
    /// relative to `path`'s own parent directory rather than leaving them
    /// relative to the process's current working directory. A service
    /// started by SCM (or a Scheduled Task) has no meaningful relationship
    /// to whatever directory the config happened to be authored in — the
    /// only stable anchor is the location of the config file itself, which
    /// the caller always knows (it's what was just read). Absolute paths in
    /// the config file are left untouched. This also means today's dev
    /// workflow (running with the default relative `config.toml`) is
    /// unaffected: an empty/relative base resolves paths exactly as before,
    /// against the current working directory.
    pub fn load(path: impl AsRef<Path>) -> Result<Self, CoreError> {
        let path = path.as_ref();
        let text = std::fs::read_to_string(path).map_err(|source| CoreError::Read {
            path: path.to_path_buf(),
            source,
        })?;
        let mut config: AgentConfig = toml::from_str(&text).map_err(|source| CoreError::Parse {
            path: path.to_path_buf(),
            source,
        })?;

        let base = path.parent().unwrap_or_else(|| Path::new(""));
        config.ca.cert_path = resolve_against(base, &config.ca.cert_path);
        config.ca.key_path = resolve_against(base, &config.ca.key_path);
        config.policy.source = resolve_against(base, &config.policy.source);
        config.logging.file_dir = resolve_against(base, &config.logging.file_dir);
        config.sysnet.pac_path = resolve_against(base, &config.sysnet.pac_path);
        config.cloud.state_dir = resolve_against(base, &config.cloud.state_dir);

        Ok(config)
    }

    /// True if `host` matches one of the configured target domains,
    /// either exactly or as a subdomain of it.
    pub fn is_target_domain(&self, host: &str) -> bool {
        let host = host.trim_end_matches('.');
        self.targets.domains.iter().any(|domain| {
            host.eq_ignore_ascii_case(domain)
                || host
                    .to_ascii_lowercase()
                    .ends_with(&format!(".{}", domain.to_ascii_lowercase()))
        })
    }
}

/// Join `p` onto `base` unless `p` is already absolute.
fn resolve_against(base: &Path, p: &Path) -> PathBuf {
    if p.is_absolute() {
        p.to_path_buf()
    } else {
        base.join(p)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn sample_config() -> AgentConfig {
        toml::from_str(
            r#"
            [proxy]
            listen_addr = "127.0.0.1"
            listen_port = 8443

            [ca]
            cert_path = "ca/root.crt"
            key_path = "ca/root.key"

            [targets]
            domains = ["claude.ai", "api.anthropic.com"]

            [policy]
            source = "policies/default.toml"
            "#,
        )
        .unwrap()
    }

    #[test]
    fn matches_exact_and_subdomain() {
        let cfg = sample_config();
        assert!(cfg.is_target_domain("claude.ai"));
        assert!(cfg.is_target_domain("CLAUDE.AI"));
        assert!(cfg.is_target_domain("www.claude.ai"));
        assert!(cfg.is_target_domain("api.anthropic.com"));
        assert!(!cfg.is_target_domain("example.com"));
        assert!(!cfg.is_target_domain("notclaude.ai"));
    }

    #[test]
    fn defaults_apply() {
        let cfg = sample_config();
        assert_eq!(cfg.proxy.max_body_bytes, 10 * 1024 * 1024);
        assert_eq!(cfg.logging.level, "info");
    }

    #[test]
    fn cloud_section_absent_means_not_configured() {
        let cfg = sample_config();
        assert!(!cfg.cloud.is_configured());
    }

    #[test]
    fn cloud_parse_install_token_splits_org_id_and_secret() {
        let org_id = Uuid::new_v4();
        let secret = "s".repeat(32);
        let cloud = CloudConfig {
            gateway_url: Some("https://gateway.example.com".to_string()),
            install_token: Some(format!("{org_id}.{secret}")),
            ..Default::default()
        };
        assert!(cloud.is_configured());

        let (parsed_org_id, parsed_secret) = cloud.parse_install_token().unwrap();
        assert_eq!(parsed_org_id, org_id);
        assert_eq!(parsed_secret, secret);
    }

    #[test]
    fn cloud_parse_install_token_rejects_missing_separator() {
        let cloud = CloudConfig {
            gateway_url: Some("https://gateway.example.com".to_string()),
            install_token: Some("no-dot-here".to_string()),
            ..Default::default()
        };
        assert!(cloud.parse_install_token().is_err());
    }

    #[test]
    fn cloud_parse_install_token_rejects_invalid_org_id() {
        let cloud = CloudConfig {
            gateway_url: Some("https://gateway.example.com".to_string()),
            install_token: Some(format!("not-a-uuid.{}", "s".repeat(32))),
            ..Default::default()
        };
        assert!(cloud.parse_install_token().is_err());
    }

    #[test]
    fn cloud_parse_install_token_rejects_short_secret() {
        let cloud = CloudConfig {
            gateway_url: Some("https://gateway.example.com".to_string()),
            install_token: Some(format!("{}.tooshort", Uuid::new_v4())),
            ..Default::default()
        };
        assert!(cloud.parse_install_token().is_err());
    }

    fn temp_dir(name: &str) -> PathBuf {
        let dir = std::env::temp_dir().join(format!("agent-core-config-test-{name}-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&dir);
        std::fs::create_dir_all(&dir).unwrap();
        dir
    }

    #[test]
    fn load_resolves_relative_paths_against_the_config_files_own_directory() {
        let dir = temp_dir("relative");
        let config_path = dir.join("config.toml");
        std::fs::write(
            &config_path,
            r#"
            [proxy]
            listen_addr = "127.0.0.1"
            listen_port = 8443

            [ca]
            cert_path = "data/ca/root.crt"
            key_path = "data/ca/root.key"

            [targets]
            domains = ["claude.ai"]

            [policy]
            source = "policies/default.toml"

            [logging]
            file_dir = "logs"

            [sysnet]
            pac_path = "data/proxy.pac"
            "#,
        )
        .unwrap();

        let cfg = AgentConfig::load(&config_path).unwrap();

        // Not relative to the process's CWD (wherever `cargo test` happens to
        // run from) — relative to the directory the config file lives in,
        // which is what a service started with an unrelated CWD needs.
        assert_eq!(cfg.ca.cert_path, dir.join("data/ca/root.crt"));
        assert_eq!(cfg.ca.key_path, dir.join("data/ca/root.key"));
        assert_eq!(cfg.policy.source, dir.join("policies/default.toml"));
        assert_eq!(cfg.logging.file_dir, dir.join("logs"));
        assert_eq!(cfg.sysnet.pac_path, dir.join("data/proxy.pac"));

        std::fs::remove_dir_all(&dir).unwrap();
    }

    #[test]
    fn load_leaves_absolute_paths_untouched() {
        let dir = temp_dir("absolute");
        let config_path = dir.join("config.toml");
        let absolute_cert = dir.join("elsewhere").join("root.crt");
        std::fs::write(
            &config_path,
            format!(
                r#"
                [proxy]
                listen_addr = "127.0.0.1"
                listen_port = 8443

                [ca]
                cert_path = {cert:?}
                key_path = "data/ca/root.key"

                [targets]
                domains = ["claude.ai"]

                [policy]
                source = "policies/default.toml"
                "#,
                cert = absolute_cert.display().to_string(),
            ),
        )
        .unwrap();

        let cfg = AgentConfig::load(&config_path).unwrap();

        assert_eq!(cfg.ca.cert_path, absolute_cert);
        assert_eq!(cfg.ca.key_path, dir.join("data/ca/root.key"));

        std::fs::remove_dir_all(&dir).unwrap();
    }
}
