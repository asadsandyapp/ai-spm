use std::path::PathBuf;

use clap::Parser;

/// AI-SPM DLP agent - local MITM proxy for AI chat traffic.
#[derive(Parser)]
struct Cli {
    /// Path to the agent's TOML config file.
    #[arg(long, default_value = "config.toml")]
    config: PathBuf,

    /// Run under the Windows Service Control Manager instead of as a plain
    /// foreground process. This is set by the service's registered start
    /// command (see `agentctl install --full`) - don't pass it by hand;
    /// running it outside of SCM fails immediately.
    #[arg(long, hide = true)]
    service: bool,
}

fn main() -> anyhow::Result<()> {
    let cli = Cli::parse();

    #[cfg(windows)]
    if cli.service {
        return agent::service::run(cli.config)
            .map_err(|e| anyhow::anyhow!("service dispatcher error: {e}"));
    }

    run_console(cli.config)
}

/// Plain foreground mode: unchanged from before the Windows Service work -
/// still what `cargo run --bin agentd` / manual dev use goes through.
fn run_console(config_path: PathBuf) -> anyhow::Result<()> {
    let runtime = tokio::runtime::Runtime::new()?;
    runtime.block_on(agent::runtime::run_agent(config_path, async {
        let _ = tokio::signal::ctrl_c().await;
    }))
}
