use std::fs;
use std::io::BufReader;
use std::path::Path;
use std::sync::RwLock;

use reqwest::header::{HeaderMap, HeaderValue, CONTENT_TYPE};
use reqwest::{Client, StatusCode};
use rustls::pki_types::{CertificateDer, PrivateKeyDer};
use rustls::{ClientConfig, RootCertStore};
use rustls_pemfile::{certs, private_key};
use serde::{Deserialize, Serialize};
use thiserror::Error;
use tracing::{debug, info, warn};
use uuid::Uuid;

use crate::config::Config;

const AGENT_API_PREFIX: &str = "/agent/v1";

#[derive(Debug, Clone, Serialize)]
pub struct RegisterRequest {
    pub hostname: String,
    pub os_version: Option<String>,
    pub agent_version: Option<String>,
    pub org_token: String,
}

#[derive(Debug, Clone, Deserialize)]
pub struct AgentResponse {
    pub id: Uuid,
    pub org_id: Uuid,
    pub hostname: String,
    pub status: String,
}

#[derive(Debug, Clone, Deserialize)]
pub struct AgentRegisterWithCertResponse {
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

#[derive(Debug, Clone, Serialize)]
pub struct PromptRequest {
    pub provider: String,
    pub model: String,
    pub messages: Vec<serde_json::Value>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub max_tokens: Option<u32>,
    /// When true, run policy/threat/PII scans only — do not call the LLM.
    #[serde(default)]
    pub inspect_only: bool,
}

#[derive(Debug, Clone, Serialize)]
pub struct WebAuditRequest {
    pub provider: String,
    #[serde(default = "default_web_model")]
    pub model: String,
    pub masked_content: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub original_content: Option<String>,
    #[serde(default)]
    pub pii_entities: Vec<String>,
    #[serde(default)]
    pub pii_hit_count: u32,
    #[serde(default = "default_web_source")]
    pub source: String,
}

fn default_web_model() -> String {
    "web-ui".to_string()
}

fn default_web_source() -> String {
    "web_mitm".to_string()
}

#[derive(Debug, Clone, Deserialize)]
pub struct WebAuditResponse {
    pub audit_event_id: Uuid,
    pub event_type: String,
}

#[derive(Debug, Clone, Deserialize)]
pub struct PromptResponse {
    pub decision: String,
    pub masked_messages: Option<Vec<serde_json::Value>>,
    pub response_content: Option<String>,
    pub audit_event_id: Option<Uuid>,
    pub blocked_reason: Option<String>,
    pub block_code: Option<String>,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct PiiPolicyPayload {
    #[serde(default)]
    pub enabled_entities: Vec<String>,
    #[serde(default = "default_mask_action")]
    pub action: String,
}

fn default_mask_action() -> String {
    "mask".to_string()
}

#[derive(Debug, Clone, Deserialize)]
struct HeartbeatResponse {
    #[serde(default)]
    status: String,
    #[serde(default)]
    pii_policy: Option<PiiPolicyPayload>,
}

#[derive(Debug, Error)]
pub enum GatewayError {
    #[error("HTTP request failed: {0}")]
    Http(#[from] reqwest::Error),
    #[error("gateway returned {status}: {body}")]
    Api { status: StatusCode, body: String },
    #[error("agent not registered: set AISPM_AGENT_ID or call register()")]
    NotRegistered,
    #[error("invalid gateway response: {0}")]
    InvalidResponse(String),
    #[error("TLS configuration failed: {0}")]
    Tls(String),
    #[error("failed to persist mTLS material: {0}")]
    Io(#[from] std::io::Error),
}

/// HTTP client for AI-SPM gateway agent API.
///
/// Sends `X-Org-ID` and `X-Agent-ID` on authenticated requests.
/// Uses mTLS client authentication when cert/key/CA paths are configured and present.
pub struct GatewayClient {
    base_url: String,
    org_id: Uuid,
    agent_id: RwLock<Option<Uuid>>,
    org_token: String,
    agent_version: String,
    mtls_cert_path: String,
    mtls_key_path: String,
    ca_cert_path: String,
    http: RwLock<Client>,
}

impl GatewayClient {
    /// Create a gateway client from configuration.
    ///
    /// When mTLS cert, key, and CA files exist at the configured paths, attaches a
    /// `rustls::ClientConfig` identity via `reqwest::ClientBuilder::use_preconfigured_tls`.
    pub fn new(config: &Config) -> Result<Self, GatewayError> {
        let mtls_cert_path = config.mtls_cert_path().to_string();
        let mtls_key_path = config.mtls_key_path().to_string();
        let ca_cert_path = config.ca_cert_path().to_string();

        let http = Self::build_http_client(&mtls_cert_path, &mtls_key_path, &ca_cert_path)?;

        Ok(Self {
            base_url: config.gateway_url.clone(),
            org_id: config.org_id,
            agent_id: RwLock::new(config.agent_id),
            org_token: config.org_token.clone(),
            agent_version: env!("CARGO_PKG_VERSION").to_string(),
            mtls_cert_path,
            mtls_key_path,
            ca_cert_path,
            http: RwLock::new(http),
        })
    }

    pub fn org_id(&self) -> Uuid {
        self.org_id
    }

    pub fn agent_id(&self) -> Option<Uuid> {
        *self.agent_id.read().expect("agent_id lock poisoned")
    }

    pub fn set_agent_id(&self, agent_id: Uuid) {
        *self.agent_id.write().expect("agent_id lock poisoned") = Some(agent_id);
    }

    pub fn clear_agent_id(&self) {
        *self.agent_id.write().expect("agent_id lock poisoned") = None;
    }

    /// Persist PEM material from registration to the configured cert paths.
    pub fn save_registration_certs(
        cert_path: &str,
        key_path: &str,
        ca_path: &str,
        certificate_pem: &str,
        private_key_pem: &str,
        ca_certificate_pem: &str,
    ) -> Result<(), GatewayError> {
        if certificate_pem.is_empty() || private_key_pem.is_empty() || ca_certificate_pem.is_empty()
        {
            return Err(GatewayError::InvalidResponse(
                "registration response missing certificate material".to_string(),
            ));
        }

        Self::write_pem_file(cert_path, certificate_pem)?;
        Self::write_pem_file(key_path, private_key_pem)?;
        Self::write_pem_file(ca_path, ca_certificate_pem)?;

        info!(
            cert_path = cert_path,
            key_path = key_path,
            ca_path = ca_path,
            "saved mTLS credentials from registration"
        );
        Ok(())
    }

    fn write_pem_file(path: &str, contents: &str) -> Result<(), GatewayError> {
        let path = Path::new(path);
        if let Some(parent) = path.parent() {
            fs::create_dir_all(parent)?;
        }
        fs::write(path, contents)?;
        Ok(())
    }

    fn build_http_client(
        cert_path: &str,
        key_path: &str,
        ca_path: &str,
    ) -> Result<Client, GatewayError> {
        let mut builder =
            Client::builder().user_agent(format!("ai-spm-agent/{}", env!("CARGO_PKG_VERSION")));

        if Path::new(cert_path).exists()
            && Path::new(key_path).exists()
            && Path::new(ca_path).exists()
        {
            let tls_config = Self::build_mtls_config(cert_path, key_path, ca_path)?;
            // Pass ClientConfig directly — wrapping in Some() makes reqwest's Any
            // downcast fail with "Unknown TLS backend".
            builder = builder.use_preconfigured_tls(tls_config);
            info!(
                cert_path = cert_path,
                key_path = key_path,
                ca_path = ca_path,
                "gateway client configured with mTLS"
            );
        } else {
            debug!(
                cert_path = cert_path,
                key_path = key_path,
                ca_path = ca_path,
                "mTLS cert files not found; using default TLS client"
            );
        }

        builder.build().map_err(GatewayError::from)
    }

    fn build_mtls_config(
        cert_path: &str,
        key_path: &str,
        ca_path: &str,
    ) -> Result<ClientConfig, GatewayError> {
        let cert_chain = Self::load_cert_chain(cert_path)?;
        let private_key = Self::load_private_key(key_path)?;
        let root_store = Self::load_root_store(ca_path)?;

        ClientConfig::builder()
            .with_root_certificates(root_store)
            .with_client_auth_cert(cert_chain, private_key)
            .map_err(|e| GatewayError::Tls(e.to_string()))
    }

    fn load_cert_chain(path: &str) -> Result<Vec<CertificateDer<'static>>, GatewayError> {
        let file = fs::File::open(path)?;
        let mut reader = BufReader::new(file);
        certs(&mut reader)
            .collect::<Result<Vec<_>, _>>()
            .map_err(|e| GatewayError::Tls(format!("failed to parse cert chain at {path}: {e}")))
    }

    fn load_private_key(path: &str) -> Result<PrivateKeyDer<'static>, GatewayError> {
        let file = fs::File::open(path)?;
        let mut reader = BufReader::new(file);
        private_key(&mut reader)
            .map_err(|e| GatewayError::Tls(format!("failed to parse private key at {path}: {e}")))?
            .ok_or_else(|| GatewayError::Tls(format!("no private key found at {path}")))
    }

    fn load_root_store(path: &str) -> Result<RootCertStore, GatewayError> {
        let file = fs::File::open(path)?;
        let mut reader = BufReader::new(file);
        let ca_certs = certs(&mut reader)
            .collect::<Result<Vec<_>, _>>()
            .map_err(|e| GatewayError::Tls(format!("failed to parse CA cert at {path}: {e}")))?;

        let mut root_store = RootCertStore::empty();
        for cert in ca_certs {
            root_store
                .add(cert)
                .map_err(|e| GatewayError::Tls(format!("failed to add CA cert: {e}")))?;
        }
        Ok(root_store)
    }

    fn reload_http_client(&self) -> Result<(), GatewayError> {
        let client = Self::build_http_client(
            &self.mtls_cert_path,
            &self.mtls_key_path,
            &self.ca_cert_path,
        )?;
        *self.http.write().expect("http lock poisoned") = client;
        Ok(())
    }

    /// Clone the current reqwest client (cheap — internally reference-counted).
    fn http_client(&self) -> Client {
        self.http.read().expect("http lock poisoned").clone()
    }

    fn url(&self, path: &str) -> String {
        format!("{}{}{}", self.base_url, AGENT_API_PREFIX, path)
    }

    fn auth_headers(&self) -> Result<HeaderMap, GatewayError> {
        let agent_id = self.agent_id().ok_or(GatewayError::NotRegistered)?;

        let mut headers = HeaderMap::new();
        headers.insert(
            "X-Org-ID",
            HeaderValue::from_str(&self.org_id.to_string())
                .map_err(|e| GatewayError::InvalidResponse(e.to_string()))?,
        );
        headers.insert(
            "X-Agent-ID",
            HeaderValue::from_str(&agent_id.to_string())
                .map_err(|e| GatewayError::InvalidResponse(e.to_string()))?,
        );
        headers.insert(CONTENT_TYPE, HeaderValue::from_static("application/json"));
        Ok(headers)
    }

    /// `POST /agent/v1/register` — first-launch agent registration.
    pub async fn register(&self) -> Result<AgentResponse, GatewayError> {
        let hostname = hostname::get()
            .map(|h| h.to_string_lossy().into_owned())
            .unwrap_or_else(|_| "unknown".to_string());

        let body = RegisterRequest {
            hostname,
            os_version: Some(std::env::consts::OS.to_string()),
            agent_version: Some(self.agent_version.clone()),
            org_token: self.org_token.clone(),
        };

        let mut headers = HeaderMap::new();
        headers.insert(
            "X-Org-ID",
            HeaderValue::from_str(&self.org_id.to_string())
                .map_err(|e| GatewayError::InvalidResponse(e.to_string()))?,
        );
        headers.insert(CONTENT_TYPE, HeaderValue::from_static("application/json"));

        let response = self
            .http_client()
            .post(self.url("/register"))
            .headers(headers)
            .json(&body)
            .send()
            .await?;

        let status = response.status();
        let body_text = response.text().await?;
        if !status.is_success() {
            return Err(GatewayError::Api {
                status,
                body: body_text,
            });
        }

        let registration: AgentRegisterWithCertResponse = serde_json::from_str(&body_text)
            .map_err(|e| GatewayError::InvalidResponse(e.to_string()))?;

        if !registration.certificate_pem.is_empty() {
            Self::save_registration_certs(
                &self.mtls_cert_path,
                &self.mtls_key_path,
                &self.ca_cert_path,
                &registration.certificate_pem,
                &registration.private_key_pem,
                &registration.ca_certificate_pem,
            )?;
            self.reload_http_client()?;
        } else {
            warn!("registration succeeded but no certificate material was returned");
        }

        self.set_agent_id(registration.id);
        debug!(agent_id = %registration.id, "agent registered with gateway");

        Ok(AgentResponse {
            id: registration.id,
            org_id: registration.org_id,
            hostname: registration.hostname,
            status: registration.status,
        })
    }

    /// `POST /agent/v1/heartbeat` — 60s health signal; may include PII policy for web MITM.
    pub async fn heartbeat(&self) -> Result<(), GatewayError> {
        let response = self
            .http_client()
            .post(self.url("/heartbeat"))
            .headers(self.auth_headers()?)
            .send()
            .await?;

        let status = response.status();
        let body = response.text().await.unwrap_or_default();
        if !status.is_success() {
            return Err(GatewayError::Api { status, body });
        }

        if let Ok(payload) = serde_json::from_str::<HeartbeatResponse>(&body) {
            if let Some(policy) = payload.pii_policy {
                if let Err(err) = Self::persist_pii_policy(&policy) {
                    warn!(error = %err, "failed to persist PII policy for web MITM");
                }
            }
        }
        Ok(())
    }

    fn persist_pii_policy(policy: &PiiPolicyPayload) -> Result<(), GatewayError> {
        let path = Path::new("/etc/ai-spm/pii-policy.json");
        if let Some(parent) = path.parent() {
            fs::create_dir_all(parent)?;
        }
        let body = serde_json::to_vec_pretty(policy).map_err(|e| {
            GatewayError::InvalidResponse(format!("serialize pii policy: {e}"))
        })?;
        fs::write(path, body)?;
        debug!(path = %path.display(), entities = ?policy.enabled_entities, "wrote web MITM PII policy");
        Ok(())
    }

    /// `POST /agent/v1/prompt` — submit intercepted prompt for policy pipeline.
    pub async fn submit_prompt(
        &self,
        request: &PromptRequest,
    ) -> Result<PromptResponse, GatewayError> {
        let response = self
            .http_client()
            .post(self.url("/prompt"))
            .headers(self.auth_headers()?)
            .json(request)
            .send()
            .await?;

        let status = response.status();
        let body_text = response.text().await?;
        if !status.is_success() {
            return Err(GatewayError::Api {
                status,
                body: body_text,
            });
        }

        serde_json::from_str(&body_text).map_err(|e| GatewayError::InvalidResponse(e.to_string()))
    }

    /// `POST /agent/v1/web-audit` — record web-UI MITM mask result (masked content only).
    pub async fn submit_web_audit(
        &self,
        request: &WebAuditRequest,
    ) -> Result<WebAuditResponse, GatewayError> {
        let response = self
            .http_client()
            .post(self.url("/web-audit"))
            .headers(self.auth_headers()?)
            .json(request)
            .send()
            .await?;

        let status = response.status();
        let body_text = response.text().await?;
        if !status.is_success() {
            return Err(GatewayError::Api {
                status,
                body: body_text,
            });
        }

        serde_json::from_str(&body_text).map_err(|e| GatewayError::InvalidResponse(e.to_string()))
    }
}
