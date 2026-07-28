//! The agent's core startup logic, independent of how the process was
//! launched. Shared between the plain foreground entrypoint (`agentd`,
//! Ctrl+C as shutdown) and the Windows Service entrypoint
//! (`agent::service`, an SCM stop/shutdown control as shutdown) - the only
//! difference between them is what `shutdown` future they pass in.

use std::future::Future;
use std::net::SocketAddr;
use std::path::PathBuf;
use std::sync::Arc;

use agent_core::config::AgentConfig;
use agent_core::policy::PolicyDoc;
use agent_dlp::RuleSet;
use agent_proxy::{DlpHandler, WsDlpHandler};
use anyhow::Context;
use hudsucker::{certificate_authority::RcgenAuthority, Proxy};
use tracing_subscriber::prelude::*;
use tracing_subscriber::EnvFilter;

/// Load config/CA/policy, serve the PAC over HTTP, and run the MITM proxy
/// until `shutdown` resolves.
pub async fn run_agent(
    config_path: PathBuf,
    shutdown: impl Future<Output = ()> + Send + 'static,
) -> anyhow::Result<()> {
    let config = AgentConfig::load(&config_path)
        .with_context(|| format!("loading config from {}", config_path.display()))?;

    // Kept alive for the whole process: the non-blocking file writer flushes
    // its background thread on drop.
    let _log_guard = init_logging(&config.logging)?;
    tracing::info!(dir = %config.logging.file_dir.display(), "writing logs to file (in addition to console)");

    let generated_ca = agent_ca::load_or_generate(&config.ca.cert_path, &config.ca.key_path)
        .context("loading/generating local CA")?;

    let policy = PolicyDoc::load(&config.policy.source)
        .with_context(|| format!("loading policy from {}", config.policy.source.display()))?;
    let ruleset = RuleSet::compile(&policy).context("compiling DLP policy")?;

    tracing::info!(rules = policy.rules.len(), "loaded DLP policy");
    tracing::info!(domains = ?config.targets.domains, "target domains configured");

    let ip: std::net::IpAddr = config
        .proxy
        .listen_addr
        .parse()
        .context("parsing proxy.listen_addr")?;
    let addr = SocketAddr::new(ip, config.proxy.listen_port);

    // Serve the PAC file over HTTP on the loopback interface. `enable-proxy`
    // points the browser's auto-config URL at this endpoint; HTTP is required
    // because Chromium browsers ignore `file://` PAC URLs.
    let pac = agent_sysnet::render_pac(
        &config.targets.domains,
        &config.proxy.listen_addr,
        config.proxy.listen_port,
    );
    let pac_addr = SocketAddr::new(ip, config.sysnet.pac_port);
    tokio::spawn(serve_pac(pac, pac_addr));

    let provider = rustls::crypto::aws_lc_rs::default_provider();
    let ca = RcgenAuthority::new(generated_ca.issuer, 1_000, provider.clone());
    let config = Arc::new(config);
    let ruleset = Arc::new(ruleset);
    let handler = DlpHandler::new(config.clone(), ruleset.clone());
    let ws_handler = WsDlpHandler::new(config, ruleset);

    let proxy = Proxy::builder()
        .with_addr(addr)
        .with_ca(ca)
        .with_rustls_connector(provider)
        .with_http_handler(handler)
        .with_websocket_handler(ws_handler)
        .with_graceful_shutdown(shutdown)
        .build()
        .map_err(|e| anyhow::anyhow!("building proxy: {e}"))?;

    tracing::info!(%addr, "starting proxy");
    proxy
        .start()
        .await
        .map_err(|e| anyhow::anyhow!("proxy error: {e}"))?;

    Ok(())
}

/// Minimal HTTP/1.1 server that returns the PAC file to any GET request on
/// `addr`. Browsers only ever fetch `/proxy.pac` from it; the same body is
/// returned regardless of path. Runs for the life of the process.
async fn serve_pac(pac: String, addr: SocketAddr) {
    use tokio::io::{AsyncReadExt, AsyncWriteExt};

    let listener = match tokio::net::TcpListener::bind(addr).await {
        Ok(listener) => listener,
        Err(err) => {
            tracing::error!(%addr, %err, "failed to bind PAC server; browser proxy auto-config will not work");
            return;
        }
    };
    tracing::info!(%addr, "serving PAC at http://{}/proxy.pac", addr);

    let response = Arc::new(format!(
        "HTTP/1.1 200 OK\r\nContent-Type: application/x-ns-proxy-autoconfig\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{}",
        pac.len(),
        pac,
    ));

    loop {
        match listener.accept().await {
            Ok((mut stream, _)) => {
                let response = response.clone();
                tokio::spawn(async move {
                    // Drain the request (we don't route on it) before replying.
                    let mut buf = [0u8; 1024];
                    let _ = stream.read(&mut buf).await;
                    let _ = stream.write_all(response.as_bytes()).await;
                    let _ = stream.shutdown().await;
                });
            }
            Err(err) => tracing::warn!(%err, "PAC server accept error"),
        }
    }
}

/// Sets up logging to both stdout and a daily-rotating file under
/// `logging.file_dir` (e.g. `logs/agentd.log.2026-07-16`). `RUST_LOG`, if
/// set, overrides `logging.level` from the config.
fn init_logging(logging: &agent_core::config::LoggingConfig) -> anyhow::Result<tracing_appender::non_blocking::WorkerGuard> {
    std::fs::create_dir_all(&logging.file_dir)
        .with_context(|| format!("creating log directory {}", logging.file_dir.display()))?;

    let file_appender = tracing_appender::rolling::daily(&logging.file_dir, "agentd.log");
    let (non_blocking, guard) = tracing_appender::non_blocking(file_appender);

    let env_filter = EnvFilter::try_from_default_env()
        .or_else(|_| EnvFilter::try_new(&logging.level))
        .unwrap_or_else(|_| EnvFilter::new("info"));

    tracing_subscriber::registry()
        .with(env_filter)
        .with(tracing_subscriber::fmt::layer())
        .with(tracing_subscriber::fmt::layer().with_ansi(false).with_writer(non_blocking))
        .init();

    Ok(guard)
}
