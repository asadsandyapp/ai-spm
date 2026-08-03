//! Cloud fleet registration: `POST /agent/v1/register` against the AI-SPM
//! control-plane, reusing the existing, already-tested backend endpoint
//! verbatim (see `backend/src/ai_spm/agent/api/v1/routes.py::register_agent`)
//! - no backend changes needed. The wire shapes here intentionally mirror
//! `agent/crates/agent-core/src/gateway/client.rs`'s `RegisterRequest`/
//! `AgentRegisterWithCertResponse`, the sibling Rust workspace's proven
//! client for this same endpoint.

use std::fs;
use std::path::Path;

use serde::{Deserialize, Serialize};
use uuid::Uuid;

use crate::error::CoreError;

const AGENT_API_PREFIX: &str = "/agent/v1";

#[derive(Debug, Clone, Serialize)]
struct RegisterRequest {
    hostname: String,
    os_version: Option<String>,
    agent_version: Option<String>,
    org_token: String,
}

/// `POST /agent/v1/register`'s response - the issued mTLS material is saved
/// for future use (policy-pull/event-reporting), not consumed by anything
/// yet.
#[derive(Debug, Clone, Deserialize)]
pub struct RegisterResponse {
    pub id: Uuid,
    pub org_id: Uuid,
    pub hostname: String,
    pub status: String,
    #[serde(default)]
    pub certificate_pem: String,
    #[serde(default)]
    pub private_key_pem: String,
    #[serde(default)]
    pub ca_certificate_pem: String,
    #[serde(default)]
    pub cert_expires_at: Option<String>,
}

#[derive(Debug, thiserror::Error)]
pub enum RegistrationError {
    #[error("HTTP request failed: {0}")]
    Http(#[from] reqwest::Error),
    #[error("gateway returned {status}: {body}")]
    Api {
        status: reqwest::StatusCode,
        body: String,
    },
    #[error("{0}")]
    InvalidToken(#[from] CoreError),
    #[error("failed to persist registration state: {0}")]
    Io(#[from] std::io::Error),
    #[error("failed to serialize registration state: {0}")]
    Serialize(#[from] serde_json::Error),
}

/// One-shot client for the registration call. Retry/backoff is the caller's
/// job (matches `agent/`'s `GatewayClient`, which keeps the same
/// separation) - this type just knows how to make the one HTTP call and
/// persist what comes back.
pub struct RegistrationClient {
    http: reqwest::Client,
    gateway_url: String,
    org_id: Uuid,
    org_token: String,
    agent_version: String,
}

impl RegistrationClient {
    pub fn new(gateway_url: impl Into<String>, org_id: Uuid, org_token: impl Into<String>) -> Self {
        Self {
            http: reqwest::Client::new(),
            gateway_url: gateway_url.into().trim_end_matches('/').to_string(),
            org_id,
            org_token: org_token.into(),
            agent_version: env!("CARGO_PKG_VERSION").to_string(),
        }
    }

    /// Build a client directly from `[cloud]` config, splitting the combined
    /// install token via [`crate::config::CloudConfig::parse_install_token`].
    pub fn from_cloud_config(cloud: &crate::config::CloudConfig) -> Result<Self, RegistrationError> {
        let gateway_url = cloud
            .gateway_url
            .clone()
            .ok_or_else(|| RegistrationError::InvalidToken(CoreError::InvalidInstallToken {
                reason: "gateway_url is not set".to_string(),
            }))?;
        let (org_id, org_token) = cloud.parse_install_token()?;
        Ok(Self::new(gateway_url, org_id, org_token))
    }

    fn url(&self, path: &str) -> String {
        format!("{}{}{}", self.gateway_url, AGENT_API_PREFIX, path)
    }

    /// `POST /agent/v1/register` - first-launch fleet registration. No CSR is
    /// sent; the backend generates the agent's keypair server-side when none
    /// is supplied (confirmed in `backend/src/ai_spm/services/cert_service.py`),
    /// so this call needs no cryptography of its own.
    pub async fn register(&self) -> Result<RegisterResponse, RegistrationError> {
        let hostname = hostname::get()
            .map(|h| h.to_string_lossy().into_owned())
            .unwrap_or_else(|_| "unknown".to_string());

        let body = RegisterRequest {
            hostname,
            os_version: Some(std::env::consts::OS.to_string()),
            agent_version: Some(self.agent_version.clone()),
            org_token: self.org_token.clone(),
        };

        let response = self
            .http
            .post(self.url("/register"))
            .header("X-Org-ID", self.org_id.to_string())
            .json(&body)
            .send()
            .await?;

        let status = response.status();
        let body_text = response.text().await?;
        if !status.is_success() {
            return Err(RegistrationError::Api {
                status,
                body: body_text,
            });
        }

        serde_json::from_str(&body_text).map_err(RegistrationError::from)
    }
}

/// Persisted local record of a completed registration - just enough to know
/// "already registered, don't call `register()` again" across restarts.
/// Deliberately kept out of `config.toml` (a tracked/shipped conffile);
/// lives under the same `data/` convention the local MITM CA already uses.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RegistrationState {
    pub agent_id: Uuid,
    pub registered_at: String,
}

/// `None` if no registration has happened yet (file missing) or the file
/// can't be read/parsed - either way, the caller's answer is "not
/// registered, try again," not a fatal error.
pub fn load_registration_state(path: &Path) -> Option<RegistrationState> {
    let text = fs::read_to_string(path).ok()?;
    serde_json::from_str(&text).ok()
}

pub fn save_registration_state(
    path: &Path,
    state: &RegistrationState,
) -> Result<(), RegistrationError> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)?;
    }
    let text = serde_json::to_string_pretty(state)?;
    fs::write(path, text)?;
    Ok(())
}

/// Save the issued mTLS material verbatim - not consumed by anything yet in
/// this task (see module docs), but written out so future policy-pull/
/// event-reporting work has it ready without also needing a persistence
/// layer.
pub fn save_registration_certs(
    cert_dir: &Path,
    response: &RegisterResponse,
) -> Result<(), RegistrationError> {
    fs::create_dir_all(cert_dir)?;
    if !response.certificate_pem.is_empty() {
        fs::write(cert_dir.join("agent.crt"), &response.certificate_pem)?;
    }
    if !response.private_key_pem.is_empty() {
        fs::write(cert_dir.join("agent.key"), &response.private_key_pem)?;
    }
    if !response.ca_certificate_pem.is_empty() {
        fs::write(cert_dir.join("ca.crt"), &response.ca_certificate_pem)?;
    }
    Ok(())
}

/// One registration attempt against `[cloud]`, persisting the result on
/// success. Shared by `agentctl register`/`install --full` (single attempt,
/// caller decides how to handle failure) and `agentd`'s startup retry loop
/// (calls this once per backoff iteration) - the persistence step must not
/// live in two places that could drift.
pub async fn register_and_persist(
    cloud: &crate::config::CloudConfig,
) -> Result<RegisterResponse, RegistrationError> {
    let client = RegistrationClient::from_cloud_config(cloud)?;
    let response = client.register().await?;

    save_registration_certs(&cloud.state_dir, &response)?;
    let state = RegistrationState {
        agent_id: response.id,
        registered_at: unix_timestamp_now(),
    };
    save_registration_state(&cloud.state_dir.join("registration.json"), &state)?;

    Ok(response)
}

/// `RegistrationState.registered_at` is informational only (never parsed
/// back), so a bare Unix-seconds string avoids pulling in a date/time crate
/// just for this.
fn unix_timestamp_now() -> String {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_secs().to_string())
        .unwrap_or_else(|_| "0".to_string())
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::config::CloudConfig;

    async fn spawn_mock_register_server(
        status: u16,
        body: String,
    ) -> (std::net::SocketAddr, tokio::task::JoinHandle<()>) {
        use tokio::io::{AsyncReadExt, AsyncWriteExt};

        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let addr = listener.local_addr().unwrap();
        let handle = tokio::spawn(async move {
            let (mut stream, _) = listener.accept().await.unwrap();
            let mut buf = [0u8; 4096];
            let _ = stream.read(&mut buf).await;
            let response = format!(
                "HTTP/1.1 {status} X\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{body}",
                body.len(),
            );
            let _ = stream.write_all(response.as_bytes()).await;
            let _ = stream.shutdown().await;
        });
        (addr, handle)
    }

    #[tokio::test]
    async fn register_parses_a_successful_response() {
        let org_id = Uuid::new_v4();
        let agent_id = Uuid::new_v4();
        let body = serde_json::json!({
            "id": agent_id,
            "org_id": org_id,
            "hostname": "test-host",
            "status": "active",
            "certificate_pem": "CERT",
            "private_key_pem": "KEY",
            "ca_certificate_pem": "CA",
            "cert_expires_at": "2027-01-01T00:00:00Z",
        })
        .to_string();
        let (addr, handle) = spawn_mock_register_server(201, body).await;

        let client = RegistrationClient::new(format!("http://{addr}"), org_id, "s".repeat(32));
        let response = client.register().await.unwrap();

        assert_eq!(response.id, agent_id);
        assert_eq!(response.org_id, org_id);
        assert_eq!(response.certificate_pem, "CERT");
        handle.await.unwrap();
    }

    #[tokio::test]
    async fn register_surfaces_an_api_error_without_panicking() {
        let org_id = Uuid::new_v4();
        let (addr, handle) =
            spawn_mock_register_server(403, r#"{"detail":"Invalid org token"}"#.to_string()).await;

        let client = RegistrationClient::new(format!("http://{addr}"), org_id, "s".repeat(32));
        let err = client.register().await.unwrap_err();

        match err {
            RegistrationError::Api { status, body } => {
                assert_eq!(status.as_u16(), 403);
                assert!(body.contains("Invalid org token"));
            }
            other => panic!("expected Api error, got {other:?}"),
        }
        handle.await.unwrap();
    }

    #[test]
    fn from_cloud_config_rejects_an_unconfigured_section() {
        let cloud = CloudConfig::default();
        assert!(RegistrationClient::from_cloud_config(&cloud).is_err());
    }

    #[test]
    fn registration_state_round_trips_through_disk() {
        let dir = std::env::temp_dir().join(format!(
            "agent-core-registration-test-{}",
            std::process::id()
        ));
        let _ = fs::remove_dir_all(&dir);
        let path = dir.join("registration.json");

        assert!(load_registration_state(&path).is_none());

        let state = RegistrationState {
            agent_id: Uuid::new_v4(),
            registered_at: "2026-08-03T00:00:00Z".to_string(),
        };
        save_registration_state(&path, &state).unwrap();

        let loaded = load_registration_state(&path).unwrap();
        assert_eq!(loaded.agent_id, state.agent_id);

        fs::remove_dir_all(&dir).unwrap();
    }
}
