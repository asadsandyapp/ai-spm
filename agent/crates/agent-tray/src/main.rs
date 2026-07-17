//! AI-SPM agent system tray — placeholder binary.
//!
//! Full Tauri 2 integration is planned in a later sprint. This stub exists so
//! the workspace layout matches IMPLEMENTATION_ROADMAP.md.

fn main() {
    tracing_subscriber::fmt()
        .with_env_filter(
            tracing_subscriber::EnvFilter::try_from_default_env()
                .unwrap_or_else(|_| tracing_subscriber::EnvFilter::new("info")),
        )
        .init();

    tracing::info!(
        version = env!("CARGO_PKG_VERSION"),
        "agent-tray placeholder — see README.md for Tauri 2 integration steps"
    );
}
