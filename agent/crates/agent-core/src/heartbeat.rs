use std::sync::Arc;
use std::time::Duration;

use thiserror::Error;
use tokio::sync::watch;
use tracing::{debug, error, info, warn};

use crate::gateway::{GatewayClient, GatewayError};
use crate::protection::enter_protection_disabled;

/// Default heartbeat interval per IMPLEMENTATION_ROADMAP (60 seconds).
pub const HEARTBEAT_INTERVAL: Duration = Duration::from_secs(60);

#[derive(Debug, Error)]
pub enum HeartbeatError {
    #[error("heartbeat loop stopped: {0}")]
    Stopped(String),
}

/// Run the periodic heartbeat loop until the shutdown signal fires.
///
/// On gateway **403 (revoked)** or **404 (deleted)**, protection is paused
/// locally (flag + tear-down) and `shutdown` is signalled so MITM tasks exit.
/// We deliberately do **not** auto re-register — that was leaving masking on
/// after an admin deleted the agent from the console.
pub async fn run_heartbeat_loop(
    client: Arc<GatewayClient>,
    mut shutdown: watch::Receiver<bool>,
    shutdown_tx: watch::Sender<bool>,
) -> Result<(), HeartbeatError> {
    info!(
        interval_secs = HEARTBEAT_INTERVAL.as_secs(),
        "starting heartbeat loop"
    );

    let mut interval = tokio::time::interval(HEARTBEAT_INTERVAL);

    loop {
        tokio::select! {
            _ = shutdown.changed() => {
                if *shutdown.borrow() {
                    info!("heartbeat loop shutting down");
                    return Ok(());
                }
            }
            _ = interval.tick() => {
                if client.agent_id().is_none() {
                    debug!("heartbeat skipped: agent not registered yet");
                    continue;
                }
                match client.heartbeat().await {
                    Ok(()) => debug!("heartbeat sent"),
                    Err(GatewayError::Api { status, .. })
                        if status.as_u16() == 403 || status.as_u16() == 404 =>
                    {
                        let reason = if status.as_u16() == 403 {
                            "revoked"
                        } else {
                            "deleted"
                        };
                        warn!(
                            status = status.as_u16(),
                            "gateway removed this agent ({reason}) — disabling local protection"
                        );
                        enter_protection_disabled(client.as_ref(), reason);
                        let _ = shutdown_tx.send(true);
                        return Ok(());
                    }
                    Err(err) => error!(error = %err, "heartbeat failed"),
                }
            }
        }
    }
}

/// Convenience helper for tests and integration harnesses.
pub async fn send_once(client: &GatewayClient) -> Result<(), crate::gateway::GatewayError> {
    client.heartbeat().await
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::config::Config;
    use uuid::Uuid;

    fn test_config(agent_id: Option<Uuid>) -> Config {
        Config {
            gateway_url: "http://localhost:65535".to_string(),
            org_token: "x".repeat(32),
            org_id: Uuid::new_v4(),
            agent_id,
            proxy_listen: "127.0.0.1:0".parse().unwrap(),
            mtls_cert_path: None,
            mtls_key_path: None,
            ca_cert_path: None,
            mitm_ca_dir: None,
            auto_configure_endpoint: false,
            auto_install_ca: false,
            auto_configure_proxy: false,
            transparent_enabled: false,
            transparent_listen: "127.0.0.1:8443".parse().unwrap(),
            auto_configure_network: false,
            explicit_proxy_enabled: false,
            socket_mark: crate::proxy::DEFAULT_SOCKET_MARK,
            mitm_domains: Vec::new(),
            local_api_enabled: false,
            local_api_listen: "127.0.0.1:8092".parse().unwrap(),
        }
    }

    #[tokio::test]
    async fn heartbeat_loop_exits_on_shutdown_without_agent_id() {
        let config = test_config(None);
        let client = Arc::new(GatewayClient::new(&config).unwrap());
        let (tx, rx) = watch::channel(false);
        let handle = tokio::spawn(run_heartbeat_loop(client, rx, tx.clone()));
        tx.send(true).unwrap();
        handle.await.unwrap().unwrap();
    }
}
