use std::path::{Path, PathBuf};

use serde::Deserialize;

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
