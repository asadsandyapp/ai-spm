use std::sync::Arc;
use std::time::Duration;

use thiserror::Error;
use tokio::sync::watch;
use tracing::{debug, error, info, warn};

use crate::gateway::{GatewayClient, GatewayError};

/// Default heartbeat interval per IMPLEMENTATION_ROADMAP (60 seconds).
pub const HEARTBEAT_INTERVAL: Duration = Duration::from_secs(60);

#[derive(Debug, Error)]
pub enum HeartbeatError {
    #[error("heartbeat loop stopped: {0}")]
    Stopped(String),
}

/// Run the periodic heartbeat loop until the shutdown signal fires.
pub async fn run_heartbeat_loop(
    client: Arc<GatewayClient>,
    mut shutdown: watch::Receiver<bool>,
) -> Result<(), HeartbeatError> {
    info!(
        interval_secs = HEARTBEAT_INTERVAL.as_secs(),
        "starting heartbeat loop"
    );

    // Note: the first `interval.tick()` completes immediately, so if the agent is
    // already registered it goes online right away. The loop must NOT exit when the
    // agent isn't registered yet — registration can complete asynchronously (see the
    // background registration retry). Skipping ticks until registered lets the agent
    // come online automatically once the gateway is reachable.
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
                    Err(GatewayError::Api { status, .. }) if status.as_u16() == 404 => {
                        // Our record was deleted on the gateway (e.g. admin removed it).
                        // Re-register so the agent reappears in the fleet and keeps protecting.
                        warn!("gateway reports agent record missing — re-registering");
                        match client.register().await {
                            Ok(agent) => info!(agent_id = %agent.id, "re-registered after record deletion"),
                            Err(reg_err) => error!(error = %reg_err, "re-registration failed; will retry"),
                        }
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
            session_token: agent_id.map(|_| "y".repeat(48)),
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
        let handle = tokio::spawn(run_heartbeat_loop(client, rx));
        tx.send(true).unwrap();
        handle.await.unwrap().unwrap();
    }
}
