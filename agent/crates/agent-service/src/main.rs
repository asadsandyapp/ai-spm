//! AI-SPM endpoint agent service — always-on daemon.
//!
//! Linux: run directly or under systemd.
//! Windows: build with `--features windows-service` for SCM integration.

use std::sync::Arc;

use agent_core::endpoint_setup::configure_endpoint;
use agent_core::heartbeat::run_heartbeat_loop;
use agent_core::local_api::run_local_api;
use agent_core::proxy::{build_proxy_state, run_explicit_proxy, run_transparent_proxy};
use agent_core::{ensure_crypto_provider, AgentStatus, Config, GatewayClient};
use thiserror::Error;
use tokio::sync::watch;
use tokio::task::JoinHandle;
use tracing::{error, info, warn};
use tracing_subscriber::{fmt, EnvFilter};

#[derive(Debug, Error)]
enum ServiceError {
    #[error("configuration error: {0}")]
    Config(#[from] agent_core::config::ConfigError),
    #[error("gateway error: {0}")]
    Gateway(#[from] agent_core::gateway::client::GatewayError),
    #[error("proxy error: {0}")]
    Proxy(#[from] agent_core::proxy::ProxyError),
    #[error("heartbeat error: {0}")]
    Heartbeat(#[from] agent_core::heartbeat::HeartbeatError),
}

fn init_logging() {
    let filter = EnvFilter::try_from_default_env()
        .unwrap_or_else(|_| EnvFilter::new("info,agent_core=debug,agent_service=debug"));

    let json_logs = std::env::var("AISPM_LOG_JSON")
        .map(|v| v == "1" || v.eq_ignore_ascii_case("true"))
        .unwrap_or(true);

    if json_logs {
        fmt()
            .json()
            .with_env_filter(filter)
            .with_current_span(false)
            .with_span_list(false)
            .init();
    } else {
        fmt().with_env_filter(filter).init();
    }
}

/// Builds the gateway client, registers (with background retry), starts every
/// enabled listener + heartbeat, and returns their join handles. Shared by the
/// plain (Linux/ctrl-c) entrypoint and the Windows SCM entrypoint so the two
/// platforms can't drift apart on registration retry / CA-failure fallback
/// behavior, the way they previously did (Windows silently dropped
/// registration errors and hard-failed on MITM CA setup instead of falling
/// back to local_api-only like Linux does).
async fn start_agent_tasks(
    shutdown_rx: watch::Receiver<bool>,
) -> Result<Vec<JoinHandle<()>>, ServiceError> {
    // Must run before GatewayClient / any rustls use (reqwest may also pull aws-lc).
    ensure_crypto_provider();

    let config = Config::load()?;
    info!(
        gateway_url = %config.gateway_url,
        org_id = %config.org_id,
        proxy_listen = %config.proxy_listen,
        agent_id = ?config.agent_id,
        "starting AI-SPM endpoint agent"
    );

    if let Err(err) = configure_endpoint(&config) {
        error!(error = %err, "endpoint auto-configuration failed; proxy will still start");
    }

    let gateway = Arc::new(GatewayClient::new(&config)?);
    let status = AgentStatus::shared();

    if gateway.agent_id().is_none() {
        info!("agent not registered — calling POST /agent/v1/register");
        match gateway.register().await {
            Ok(agent) => info!(agent_id = %agent.id, status = %agent.status, "registered"),
            Err(err) => {
                error!(error = %err, "initial registration failed; retrying in background until gateway is reachable");
            }
        }
    }

    // Self-healing registration: if the gateway was unreachable at startup (e.g. the
    // backend came up after the agent), keep retrying so prompts don't fail open forever.
    if gateway.agent_id().is_none() {
        let reg_gateway = Arc::clone(&gateway);
        let mut reg_shutdown = shutdown_rx.clone();
        tokio::spawn(async move {
            let mut backoff = std::time::Duration::from_secs(5);
            let max_backoff = std::time::Duration::from_secs(60);
            loop {
                if reg_gateway.agent_id().is_some() {
                    break;
                }
                tokio::select! {
                    _ = tokio::time::sleep(backoff) => {}
                    _ = reg_shutdown.changed() => break,
                }
                if reg_gateway.agent_id().is_some() {
                    break;
                }
                match reg_gateway.register().await {
                    Ok(agent) => {
                        info!(agent_id = %agent.id, status = %agent.status, "registered (background retry)");
                        break;
                    }
                    Err(err) => {
                        warn!(error = %err, "background registration retry failed; will retry");
                        backoff = (backoff * 2).min(max_backoff);
                    }
                }
            }
        });
    }

    // MITM CA is only required for transparent / explicit proxy. Local-api (extension)
    // must still start if CA files are unreadable — otherwise the service crash-loops
    // and ChatGPT/Claude/Gemini masking dies with it.
    let need_mitm = config.transparent_enabled || config.explicit_proxy_enabled;
    let proxy_state = if need_mitm {
        match build_proxy_state(
            Arc::clone(&gateway),
            config.mitm_ca_dir(),
            config.mitm_domains.clone(),
            Arc::clone(&status),
        ) {
            Ok(state) => Some(state),
            Err(err) => {
                error!(
                    error = %err,
                    ca_dir = %config.mitm_ca_dir().display(),
                    "MITM CA unavailable — transparent/explicit proxy disabled"
                );
                if !config.local_api_enabled {
                    return Err(err.into());
                }
                warn!("continuing with local_api + heartbeat only (fix CA permissions under /etc/ai-spm/certs)");
                None
            }
        }
    } else {
        None
    };
    let mut handles = Vec::new();

    if config.transparent_enabled {
        if let Some(ref proxy_state) = proxy_state {
            info!(
                listen = %config.transparent_listen,
                "starting transparent network interceptor (enterprise mode)"
            );
            let transparent_state = Arc::clone(proxy_state);
            let transparent_listen = config.transparent_listen;
            let socket_mark = config.socket_mark;
            let transparent_shutdown = shutdown_rx.clone();
            handles.push(tokio::spawn(async move {
                if let Err(err) = run_transparent_proxy(
                    transparent_listen,
                    transparent_state,
                    socket_mark,
                    transparent_shutdown,
                )
                .await
                {
                    error!(error = %err, "transparent interceptor exited with error");
                }
            }));
        } else {
            warn!("AISPM_TRANSPARENT_ENABLED but MITM CA failed — skipping transparent listener");
        }
    }

    if config.explicit_proxy_enabled {
        if let Some(ref proxy_state) = proxy_state {
            info!(
                listen = %config.proxy_listen,
                "starting explicit HTTP proxy (legacy mode)"
            );
            let explicit_state = Arc::clone(proxy_state);
            let explicit_listen = config.proxy_listen;
            let explicit_shutdown = shutdown_rx.clone();
            handles.push(tokio::spawn(async move {
                if let Err(err) =
                    run_explicit_proxy(explicit_listen, explicit_state, explicit_shutdown).await
                {
                    error!(error = %err, "explicit proxy exited with error");
                }
            }));
        } else {
            warn!("AISPM_EXPLICIT_PROXY_ENABLED but MITM CA failed — skipping explicit proxy");
        }
    }

    // Localhost bridge for web-MITM audit (+ legacy extension inspect). Always on
    // when transparent MITM is enabled so ChatGPT web masks appear in Admin Audit.
    let start_local_api = config.local_api_enabled || config.transparent_enabled;
    if start_local_api {
        info!(
            listen = %config.local_api_listen,
            legacy = config.local_api_enabled,
            "starting local API (web-audit bridge on 127.0.0.1)"
        );
        let local_api_gateway = Arc::clone(&gateway);
        let local_api_status = Arc::clone(&status);
        let local_api_listen = config.local_api_listen;
        let local_api_shutdown = shutdown_rx.clone();
        handles.push(tokio::spawn(async move {
            if let Err(err) = run_local_api(
                local_api_listen,
                local_api_gateway,
                local_api_status,
                local_api_shutdown,
            )
            .await
            {
                error!(error = %err, "local inspection API exited with error");
            }
        }));
    } else {
        warn!(
            listen = %config.local_api_listen,
            "local API not started — agent-tray's GET /status will be unreachable until AISPM_LOCAL_API_ENABLED=1 or transparent mode is on"
        );
    }

    if !config.transparent_enabled && !config.explicit_proxy_enabled && !config.local_api_enabled {
        warn!("no interception mode enabled — set AISPM_TRANSPARENT_ENABLED=1, AISPM_EXPLICIT_PROXY_ENABLED=1, or AISPM_LOCAL_API_ENABLED=1");
    }

    let heartbeat_gateway = Arc::clone(&gateway);
    let heartbeat_status = Arc::clone(&status);
    let heartbeat_shutdown = shutdown_rx.clone();
    let heartbeat_handle = tokio::spawn(async move {
        if let Err(err) =
            run_heartbeat_loop(heartbeat_gateway, heartbeat_status, heartbeat_shutdown).await
        {
            error!(error = %err, "heartbeat loop exited with error");
        }
    });
    handles.push(heartbeat_handle);

    Ok(handles)
}

async fn run_agent() -> Result<(), ServiceError> {
    let (shutdown_tx, shutdown_rx) = watch::channel(false);
    let handles = start_agent_tasks(shutdown_rx).await?;

    tokio::signal::ctrl_c()
        .await
        .expect("failed to listen for ctrl-c");
    info!("shutdown signal received");
    let _ = shutdown_tx.send(true);

    for handle in handles {
        let _ = handle.await;
    }
    info!("agent service stopped");
    Ok(())
}

#[cfg(all(windows, feature = "windows-service"))]
mod windows_svc {
    use super::*;
    use std::ffi::OsString;
    use std::time::Duration;
    use windows_service::service::{
        ServiceControl, ServiceControlAccept, ServiceExitCode, ServiceState, ServiceStatus,
        ServiceType,
    };
    use windows_service::service_control_handler::{self, ServiceControlHandlerResult};
    use windows_service::service_dispatcher;

    const SERVICE_NAME: &str = "AiSpmAgent";
    const SERVICE_TYPE: ServiceType = ServiceType::OWN_PROCESS;

    // service_dispatcher::start needs an `extern "system"` FFI callback, not a
    // plain Rust fn - this macro generates that wrapper (named ffi_service_main
    // below) around service_main. Without it this is a type mismatch at compile
    // time (E0308: expected "system" fn, found "Rust" fn) - caught by actually
    // building with --features windows-service for the MSI, since the plain
    // `cargo build --workspace` in agent-ci.yml's `test` job never enables it.
    windows_service::define_windows_service!(ffi_service_main, service_main);

    pub fn run() -> windows_service::Result<()> {
        service_dispatcher::start(SERVICE_NAME, ffi_service_main)
    }

    fn service_main(_arguments: Vec<OsString>) {
        if let Err(err) = run_service() {
            error!(error = %err, "windows service failed");
        }
    }

    fn run_service() -> windows_service::Result<()> {
        let (shutdown_tx, shutdown_rx) = watch::channel(false);

        let event_handler = {
            let shutdown_tx = shutdown_tx.clone();
            move |control_event| -> ServiceControlHandlerResult {
                match control_event {
                    ServiceControl::Stop => {
                        let _ = shutdown_tx.send(true);
                        ServiceControlHandlerResult::NoError
                    }
                    ServiceControl::Interrogate => ServiceControlHandlerResult::NoError,
                    _ => ServiceControlHandlerResult::NotImplemented,
                }
            }
        };

        let status_handle = service_control_handler::register(SERVICE_NAME, event_handler)?;

        status_handle.set_service_status(ServiceStatus {
            service_type: SERVICE_TYPE,
            current_state: ServiceState::Running,
            controls_accepted: ServiceControlAccept::STOP,
            exit_code: ServiceExitCode::Win32(0),
            checkpoint: 0,
            wait_hint: Duration::default(),
            process_id: None,
        })?;

        let rt = tokio::runtime::Builder::new_multi_thread()
            .enable_all()
            .build()
            .expect("tokio runtime");

        rt.block_on(async {
            init_logging();
            if let Err(err) = run_agent_with_shutdown(shutdown_rx).await {
                error!(error = %err, "agent runtime error");
            }
        });

        status_handle.set_service_status(ServiceStatus {
            service_type: SERVICE_TYPE,
            current_state: ServiceState::Stopped,
            controls_accepted: ServiceControlAccept::empty(),
            exit_code: ServiceExitCode::Win32(0),
            checkpoint: 0,
            wait_hint: Duration::default(),
            process_id: None,
        })?;

        Ok(())
    }

    async fn run_agent_with_shutdown(
        mut shutdown_rx: watch::Receiver<bool>,
    ) -> Result<(), ServiceError> {
        // Windows SCM path shares start_agent_tasks with the Linux/ctrl-c path so
        // registration retry-with-backoff and the MITM-CA-failure→local_api-only
        // fallback behave identically on both platforms instead of Windows
        // silently dropping registration errors and hard-failing on CA setup.
        let handles = start_agent_tasks(shutdown_rx.clone()).await?;

        shutdown_rx.changed().await.ok();
        for handle in handles {
            let _ = handle.await;
        }
        Ok(())
    }
}

#[cfg(all(windows, feature = "windows-service"))]
fn main() -> Result<(), Box<dyn std::error::Error>> {
    windows_svc::run()?;
    Ok(())
}

#[cfg(not(all(windows, feature = "windows-service")))]
#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    init_logging();
    run_agent().await?;
    Ok(())
}
