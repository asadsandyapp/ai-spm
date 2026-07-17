use std::env;
use std::fs;
use std::net::SocketAddr;
use std::path::Path;

use serde::{Deserialize, Serialize};
use thiserror::Error;
use uuid::Uuid;

/// Default transparent interceptor listen address (iptables REDIRECT target).
pub const DEFAULT_TRANSPARENT_LISTEN: &str = "0.0.0.0:9443";

/// Default local explicit proxy listen address (optional dev / legacy mode).
pub const DEFAULT_PROXY_LISTEN: &str = "127.0.0.1:8080";

/// Default localhost inspection API address for the managed browser extension.
pub const DEFAULT_LOCAL_API_LISTEN: &str = "127.0.0.1:8092";

/// Default gateway URL for local development.
pub const DEFAULT_GATEWAY_URL: &str = "http://localhost:8000";

#[cfg(unix)]
pub const DEFAULT_MTLS_CERT_PATH: &str = "/etc/ai-spm/certs/agent.crt";
#[cfg(unix)]
pub const DEFAULT_MTLS_KEY_PATH: &str = "/etc/ai-spm/certs/agent.key";
#[cfg(unix)]
pub const DEFAULT_MTLS_CA_PATH: &str = "/etc/ai-spm/certs/ca.crt";
#[cfg(unix)]
pub const DEFAULT_MITM_CA_DIR: &str = "/etc/ai-spm/certs/mitm";

#[cfg(windows)]
pub const DEFAULT_MTLS_CERT_PATH: &str = r"C:\ProgramData\AISPM\certs\agent.crt";
#[cfg(windows)]
pub const DEFAULT_MTLS_KEY_PATH: &str = r"C:\ProgramData\AISPM\certs\agent.key";
#[cfg(windows)]
pub const DEFAULT_MTLS_CA_PATH: &str = r"C:\ProgramData\AISPM\certs\ca.crt";
#[cfg(windows)]
pub const DEFAULT_MITM_CA_DIR: &str = r"C:\ProgramData\AISPM\certs\mitm";

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ConfigFile {
    pub gateway_url: Option<String>,
    pub org_token: Option<String>,
    pub org_id: Option<String>,
    pub agent_id: Option<String>,
    pub proxy_listen: Option<String>,
    pub mtls_cert_path: Option<String>,
    pub mtls_key_path: Option<String>,
    pub ca_cert_path: Option<String>,
    pub mitm_ca_dir: Option<String>,
    pub auto_configure_endpoint: Option<bool>,
    pub auto_install_ca: Option<bool>,
    pub auto_configure_proxy: Option<bool>,
    pub transparent_enabled: Option<bool>,
    pub transparent_listen: Option<String>,
    pub auto_configure_network: Option<bool>,
    pub explicit_proxy_enabled: Option<bool>,
    pub socket_mark: Option<u32>,
    pub mitm_domains: Option<Vec<String>>,
    pub local_api_enabled: Option<bool>,
    pub local_api_listen: Option<String>,
}

#[derive(Debug, Clone)]
pub struct Config {
    pub gateway_url: String,
    pub org_token: String,
    pub org_id: Uuid,
    pub agent_id: Option<Uuid>,
    pub proxy_listen: SocketAddr,
    pub mtls_cert_path: Option<String>,
    pub mtls_key_path: Option<String>,
    pub ca_cert_path: Option<String>,
    pub mitm_ca_dir: Option<String>,
    pub auto_configure_endpoint: bool,
    pub auto_install_ca: bool,
    pub auto_configure_proxy: bool,
    pub transparent_enabled: bool,
    pub transparent_listen: SocketAddr,
    pub auto_configure_network: bool,
    pub explicit_proxy_enabled: bool,
    pub socket_mark: u32,
    pub mitm_domains: Vec<String>,
    pub local_api_enabled: bool,
    pub local_api_listen: SocketAddr,
}

#[derive(Debug, Error)]
pub enum ConfigError {
    #[error("missing required configuration: {0}")]
    Missing(&'static str),
    #[error("invalid configuration value for {field}: {message}")]
    Invalid {
        field: &'static str,
        message: String,
    },
    #[error("failed to read config file: {0}")]
    Io(#[from] std::io::Error),
    #[error("failed to parse config file: {0}")]
    Parse(#[from] serde_json::Error),
}

impl Config {
    /// Load configuration from environment variables, optionally merged with a JSON file.
    ///
    /// Environment variables (file values are overridden by env):
    /// - `AISPM_GATEWAY_URL` — gateway base URL (no trailing slash)
    /// - `AISPM_ORG_TOKEN` — organization registration token
    /// - `AISPM_ORG_ID` — organization UUID
    /// - `AISPM_AGENT_ID` — agent UUID (optional until registered)
    /// - `AISPM_PROXY_LISTEN` — local proxy bind address (default `127.0.0.1:8080`)
    /// - `AISPM_CONFIG_FILE` — path to JSON config file
    /// - `AISPM_MTLS_CERT` / `AISPM_MTLS_KEY` / `AISPM_MTLS_CA` — mTLS cert paths
    pub fn load() -> Result<Self, ConfigError> {
        let file_cfg = Self::load_file_from_env()?;
        let gateway_url = env::var("AISPM_GATEWAY_URL")
            .ok()
            .or_else(|| file_cfg.as_ref().and_then(|f| f.gateway_url.clone()))
            .unwrap_or_else(|| DEFAULT_GATEWAY_URL.to_string());

        let org_token = env::var("AISPM_ORG_TOKEN")
            .ok()
            .or_else(|| file_cfg.as_ref().and_then(|f| f.org_token.clone()))
            .ok_or(ConfigError::Missing(
                "AISPM_ORG_TOKEN (or org_token in config file)",
            ))?;

        let org_id = Self::parse_uuid(
            &env::var("AISPM_ORG_ID")
                .ok()
                .or_else(|| file_cfg.as_ref().and_then(|f| f.org_id.clone()))
                .ok_or(ConfigError::Missing(
                    "AISPM_ORG_ID (or org_id in config file)",
                ))?,
            "org_id",
        )?;

        let agent_id = match env::var("AISPM_AGENT_ID")
            .ok()
            .or_else(|| file_cfg.as_ref().and_then(|f| f.agent_id.clone()))
        {
            Some(value) => Some(Self::parse_uuid(&value, "agent_id")?),
            None => None,
        };

        let proxy_listen = env::var("AISPM_PROXY_LISTEN")
            .ok()
            .or_else(|| file_cfg.as_ref().and_then(|f| f.proxy_listen.clone()))
            .unwrap_or_else(|| DEFAULT_PROXY_LISTEN.to_string());
        let proxy_listen =
            proxy_listen
                .parse::<SocketAddr>()
                .map_err(|e| ConfigError::Invalid {
                    field: "proxy_listen",
                    message: e.to_string(),
                })?;

        let mtls_cert_path = env::var("AISPM_MTLS_CERT")
            .ok()
            .or_else(|| file_cfg.as_ref().and_then(|f| f.mtls_cert_path.clone()));
        let mtls_key_path = env::var("AISPM_MTLS_KEY")
            .ok()
            .or_else(|| file_cfg.as_ref().and_then(|f| f.mtls_key_path.clone()));
        let ca_cert_path = env::var("AISPM_MTLS_CA")
            .ok()
            .or_else(|| file_cfg.as_ref().and_then(|f| f.ca_cert_path.clone()));
        let mitm_ca_dir = env::var("AISPM_MITM_CA_DIR")
            .ok()
            .or_else(|| file_cfg.as_ref().and_then(|f| f.mitm_ca_dir.clone()));
        let auto_configure_endpoint = Self::bool_setting(
            "AISPM_AUTO_CONFIGURE_ENDPOINT",
            file_cfg.as_ref().and_then(|f| f.auto_configure_endpoint),
            true,
        )?;
        let auto_install_ca = Self::bool_setting(
            "AISPM_AUTO_INSTALL_CA",
            file_cfg.as_ref().and_then(|f| f.auto_install_ca),
            auto_configure_endpoint,
        )?;
        let auto_configure_proxy = Self::bool_setting(
            "AISPM_AUTO_CONFIGURE_PROXY",
            file_cfg.as_ref().and_then(|f| f.auto_configure_proxy),
            false,
        )?;
        let transparent_enabled = Self::bool_setting(
            "AISPM_TRANSPARENT_ENABLED",
            file_cfg.as_ref().and_then(|f| f.transparent_enabled),
            cfg!(target_os = "linux"),
        )?;
        let transparent_listen = env::var("AISPM_TRANSPARENT_LISTEN")
            .ok()
            .or_else(|| file_cfg.as_ref().and_then(|f| f.transparent_listen.clone()))
            .unwrap_or_else(|| DEFAULT_TRANSPARENT_LISTEN.to_string());
        let transparent_listen =
            transparent_listen
                .parse::<SocketAddr>()
                .map_err(|e| ConfigError::Invalid {
                    field: "transparent_listen",
                    message: e.to_string(),
                })?;
        let auto_configure_network = Self::bool_setting(
            "AISPM_AUTO_CONFIGURE_NETWORK",
            file_cfg.as_ref().and_then(|f| f.auto_configure_network),
            transparent_enabled,
        )?;
        let explicit_proxy_enabled = Self::bool_setting(
            "AISPM_EXPLICIT_PROXY_ENABLED",
            file_cfg.as_ref().and_then(|f| f.explicit_proxy_enabled),
            false,
        )?;
        let socket_mark = env::var("AISPM_SOCKET_MARK")
            .ok()
            .and_then(|v| {
                if let Some(hex) = v.strip_prefix("0x") {
                    u32::from_str_radix(hex, 16).ok()
                } else {
                    v.parse().ok()
                }
            })
            .or(file_cfg.as_ref().and_then(|f| f.socket_mark))
            .unwrap_or(crate::proxy::DEFAULT_SOCKET_MARK);

        let mitm_domains = env::var("AISPM_MITM_DOMAINS")
            .ok()
            .map(|v| {
                v.split(',')
                    .map(|s| s.trim().to_ascii_lowercase())
                    .filter(|s| !s.is_empty())
                    .collect::<Vec<_>>()
            })
            .or_else(|| file_cfg.as_ref().and_then(|f| f.mitm_domains.clone()))
            .unwrap_or_else(|| {
                crate::proxy::DEFAULT_MITM_DOMAINS
                    .iter()
                    .map(|s| s.to_string())
                    .collect()
            });

        let local_api_enabled = Self::bool_setting(
            "AISPM_LOCAL_API_ENABLED",
            file_cfg.as_ref().and_then(|f| f.local_api_enabled),
            true,
        )?;
        let local_api_listen = env::var("AISPM_LOCAL_API_LISTEN")
            .ok()
            .or_else(|| file_cfg.as_ref().and_then(|f| f.local_api_listen.clone()))
            .unwrap_or_else(|| DEFAULT_LOCAL_API_LISTEN.to_string());
        let local_api_listen =
            local_api_listen
                .parse::<SocketAddr>()
                .map_err(|e| ConfigError::Invalid {
                    field: "local_api_listen",
                    message: e.to_string(),
                })?;

        Ok(Self {
            gateway_url: gateway_url.trim_end_matches('/').to_string(),
            org_token,
            org_id,
            agent_id,
            proxy_listen,
            mtls_cert_path,
            mtls_key_path,
            ca_cert_path,
            mitm_ca_dir,
            auto_configure_endpoint,
            auto_install_ca,
            auto_configure_proxy,
            transparent_enabled,
            transparent_listen,
            auto_configure_network,
            explicit_proxy_enabled,
            socket_mark,
            mitm_domains,
            local_api_enabled,
            local_api_listen,
        })
    }

    pub fn mtls_cert_path(&self) -> &str {
        self.mtls_cert_path
            .as_deref()
            .unwrap_or(DEFAULT_MTLS_CERT_PATH)
    }

    pub fn mtls_key_path(&self) -> &str {
        self.mtls_key_path
            .as_deref()
            .unwrap_or(DEFAULT_MTLS_KEY_PATH)
    }

    pub fn ca_cert_path(&self) -> &str {
        self.ca_cert_path.as_deref().unwrap_or(DEFAULT_MTLS_CA_PATH)
    }

    /// Directory for the MITM root CA and dynamically issued leaf certificates.
    pub fn mitm_ca_dir(&self) -> std::path::PathBuf {
        if let Some(ref path) = self.mitm_ca_dir {
            return std::path::PathBuf::from(path);
        }
        if let Ok(home) = env::var("HOME") {
            return std::path::PathBuf::from(home).join(".local/share/ai-spm/mitm");
        }
        std::path::PathBuf::from(DEFAULT_MITM_CA_DIR)
    }

    pub fn with_agent_id(mut self, agent_id: Uuid) -> Self {
        self.agent_id = Some(agent_id);
        self
    }

    fn load_file_from_env() -> Result<Option<ConfigFile>, ConfigError> {
        let path = match env::var("AISPM_CONFIG_FILE") {
            Ok(path) => path,
            Err(_) => return Ok(None),
        };
        Self::load_file(Path::new(&path))
    }

    fn load_file(path: &Path) -> Result<Option<ConfigFile>, ConfigError> {
        if !path.exists() {
            return Ok(None);
        }
        let contents = fs::read_to_string(path)?;
        let cfg: ConfigFile = serde_json::from_str(&contents)?;
        Ok(Some(cfg))
    }

    fn parse_uuid(value: &str, field: &'static str) -> Result<Uuid, ConfigError> {
        Uuid::parse_str(value).map_err(|e| ConfigError::Invalid {
            field,
            message: e.to_string(),
        })
    }

    fn bool_setting(
        env_name: &'static str,
        file_value: Option<bool>,
        default: bool,
    ) -> Result<bool, ConfigError> {
        match env::var(env_name) {
            Ok(value) => Self::parse_bool(&value, env_name),
            Err(_) => Ok(file_value.unwrap_or(default)),
        }
    }

    fn parse_bool(value: &str, field: &'static str) -> Result<bool, ConfigError> {
        match value.trim().to_ascii_lowercase().as_str() {
            "1" | "true" | "yes" | "on" => Ok(true),
            "0" | "false" | "no" | "off" => Ok(false),
            _ => Err(ConfigError::Invalid {
                field,
                message: format!("expected boolean, got {value:?}"),
            }),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_proxy_listen_default_shape() {
        let addr: SocketAddr = DEFAULT_PROXY_LISTEN.parse().unwrap();
        assert_eq!(addr.port(), 8080);
    }
}
