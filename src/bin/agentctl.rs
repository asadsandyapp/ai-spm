use std::path::{Path, PathBuf};

use agent_core::config::AgentConfig;
use anyhow::Context;
use clap::{Parser, Subcommand};

/// AI-SPM DLP agent control CLI.
#[derive(Parser)]
struct Cli {
    /// Path to the agent's TOML config file.
    #[arg(long, default_value = "config.toml", global = true)]
    config: PathBuf,

    #[command(subcommand)]
    command: Command,
}

#[derive(Subcommand)]
enum Command {
    /// Generate (if needed) the local root CA and install it into the
    /// current user's Trusted Root store.
    InstallCa,
    /// Write a PAC file scoped to `[targets].domains` and point the current
    /// user's browser proxy at it, so only that traffic goes through the
    /// agent - everything else goes DIRECT, bypassing it entirely.
    EnableProxy,
    /// Revert the current user's proxy configuration (undoes `enable-proxy`).
    DisableProxy,
    /// Print the current config and CA/policy state.
    Status,
    /// Full production install: CA into the Local Machine Trusted Root
    /// store, Firefox enterprise trust, and `agentd` registered as an
    /// auto-start Windows Service with crash-restart recovery actions.
    /// Requires an elevated process. This is what the MSI installer's
    /// custom action runs - the granular subcommands above stay as they
    /// were for dev/test/troubleshooting.
    Install {
        /// Perform the full production install. Currently the only
        /// supported mode - the flag exists so the installer's invocation
        /// reads self-documenting and to leave room for a lighter-weight
        /// mode later without a breaking CLI change.
        #[arg(long)]
        full: bool,
    },
    /// Undo `install --full`: stop and remove the Windows Service, and
    /// best-effort remove the Local Machine CA certificate. Requires an
    /// elevated process. Per-user state from `enable-proxy` is untouched -
    /// each user should run `disable-proxy` themselves first.
    Uninstall,
}

fn main() -> anyhow::Result<()> {
    tracing_subscriber::fmt::init();
    let cli = Cli::parse();

    // Config is only loaded for the subcommands that actually need it - in
    // particular `uninstall` must not depend on it. It's driven by an MSI
    // deferred custom action whose working directory isn't guaranteed to be
    // the install directory, so a `cli.config` default of the relative
    // "config.toml" would fail to load there for no reason (this was found
    // via a real `msiexec /x` test: the custom action ran but exited 1
    // because of exactly this).
    match cli.command {
        Command::InstallCa => install_ca(&load_config(&cli.config)?),
        Command::EnableProxy => enable_proxy(&load_config(&cli.config)?),
        Command::DisableProxy => disable_proxy(),
        Command::Status => status(&load_config(&cli.config)?),
        Command::Install { full } => install_full(&load_config(&cli.config)?, &cli.config, full),
        Command::Uninstall => uninstall_full(),
    }
}

fn load_config(path: &Path) -> anyhow::Result<AgentConfig> {
    AgentConfig::load(path).with_context(|| format!("loading config from {}", path.display()))
}

fn install_ca(config: &AgentConfig) -> anyhow::Result<()> {
    let generated = agent_ca::load_or_generate(&config.ca.cert_path, &config.ca.key_path)
        .context("loading/generating local CA")?;

    #[cfg(windows)]
    {
        agent_ca::install_root_cert(&generated.cert_der, agent_ca::StoreScope::CurrentUser)
            .context("installing CA into current-user Root store")?;
        println!(
            "Installed AI-SPM DLP Agent CA into the current user's Trusted Root store.\nCertificate: {}",
            config.ca.cert_path.display()
        );
        install_firefox_trust();
    }

    #[cfg(not(windows))]
    {
        let _ = &generated;
        println!(
            "CA generated at {}, but trust-store install is only implemented on Windows.",
            config.ca.cert_path.display()
        );
    }

    Ok(())
}

/// Firefox ignores the Windows certificate stores, so `install_root_cert`
/// above has no effect on it. Set the `ImportEnterpriseRoots` enterprise
/// policy on every Firefox install found so it trusts the OS stores
/// instead - see `agent_ca::firefox` for why. Best-effort: a Firefox that
/// isn't found or can't be written to (machine-wide install, no admin) is
/// reported but doesn't fail `install-ca` for everything else.
#[cfg(windows)]
fn install_firefox_trust() {
    let install_dirs = agent_ca::firefox::find_install_dirs();
    if install_dirs.is_empty() {
        println!("Firefox not found on this machine; skipping Firefox trust setup.");
        return;
    }

    for dir in install_dirs {
        match agent_ca::firefox::install_enterprise_policy(&dir) {
            Ok(policies_path) => println!(
                "Firefox: enabled ImportEnterpriseRoots via {} (install at {}).\nRestart Firefox to pick it up.",
                policies_path.display(),
                dir.display(),
            ),
            Err(err) => println!(
                "Firefox: could not write policy for install at {} ({err}). If this is a \
                 machine-wide install (under Program Files), re-run as Administrator to cover it.",
                dir.display(),
            ),
        }
    }
}

fn enable_proxy(config: &AgentConfig) -> anyhow::Result<()> {
    let pac = agent_sysnet::render_pac(
        &config.targets.domains,
        &config.proxy.listen_addr,
        config.proxy.listen_port,
    );

    if let Some(parent) = config.sysnet.pac_path.parent() {
        std::fs::create_dir_all(parent)
            .with_context(|| format!("creating directory {}", parent.display()))?;
    }
    std::fs::write(&config.sysnet.pac_path, pac)
        .with_context(|| format!("writing PAC file to {}", config.sysnet.pac_path.display()))?;

    let abs_path = std::path::absolute(&config.sysnet.pac_path)
        .context("resolving absolute path to PAC file")?;

    // The PAC is served over HTTP by `agentd` (Chromium browsers ignore
    // `file://` PAC URLs). The disk copy is kept only for inspection.
    let pac_url = format!(
        "http://{}:{}/proxy.pac",
        config.proxy.listen_addr, config.sysnet.pac_port
    );

    #[cfg(windows)]
    {
        agent_sysnet::set_pac_url(&pac_url).context("setting current-user proxy auto-config URL")?;
        println!(
            "Enabled: only {:?} now route through the agent at {}:{}.\nPAC URL: {} (served by agentd; disk copy at {})\nEverything else bypasses the proxy (DIRECT).\nStart agentd if it isn't running, then restart your browser to pick up the change; run `agentctl disable-proxy` to revert.",
            config.targets.domains,
            config.proxy.listen_addr,
            config.proxy.listen_port,
            pac_url,
            abs_path.display(),
        );
    }

    #[cfg(not(windows))]
    {
        let _ = &pac_url;
        println!(
            "PAC file written to {}, but system proxy configuration is only implemented on Windows.",
            abs_path.display()
        );
    }

    Ok(())
}

fn disable_proxy() -> anyhow::Result<()> {
    #[cfg(windows)]
    {
        agent_sysnet::clear_pac_url().context("clearing current-user proxy auto-config URL")?;
        println!("Disabled: proxy auto-config cleared. Restart your browser to pick up the change.");
    }

    #[cfg(not(windows))]
    {
        println!("System proxy configuration is only implemented on Windows; nothing to disable.");
    }

    Ok(())
}

/// Drives the whole production install: CA into the Local Machine store
/// (covers every account on the box, not just the invoking user), Firefox
/// enterprise trust, and `agentd` registered as an auto-start Windows
/// Service. Everything here needs an elevated process; `agent_ca`'s Windows
/// API calls will fail with access-denied errors if it isn't.
fn install_full(config: &AgentConfig, config_path: &Path, full: bool) -> anyhow::Result<()> {
    anyhow::ensure!(
        full,
        "`agentctl install` currently only supports `--full`; run `agentctl install --full`."
    );

    let generated = agent_ca::load_or_generate(&config.ca.cert_path, &config.ca.key_path)
        .context("loading/generating local CA")?;

    #[cfg(windows)]
    {
        agent_ca::install_root_cert(&generated.cert_der, agent_ca::StoreScope::LocalMachine).context(
            "installing CA into the Local Machine Trusted Root store (this requires an elevated/admin process)",
        )?;
        println!("Installed AI-SPM DLP Agent CA into the Local Machine Trusted Root store.");

        install_firefox_trust();

        // The service registration needs an absolute config path - SCM
        // starts `agentd.exe` with no meaningful relationship to whatever
        // directory `agentctl install --full` happened to be run from.
        let absolute_config_path =
            std::path::absolute(config_path).context("resolving absolute path to config file")?;
        let agentd_exe = std::env::current_exe()
            .context("locating agentctl.exe")?
            .with_file_name("agentd.exe");
        anyhow::ensure!(
            agentd_exe.exists(),
            "expected to find agentd.exe next to agentctl.exe at {}",
            agentd_exe.display()
        );

        agent::service_install::install(&agentd_exe, &absolute_config_path)
            .context("registering the AI-SPM DLP Agent Windows Service")?;
        println!(
            "Registered and started the '{}' Windows Service (auto-start, crash-restart on failure).",
            agent::SERVICE_DISPLAY_NAME
        );
        println!(
            "Each user still needs to run `agentctl enable-proxy` once (no admin required) to point \
             their own browser at the agent."
        );
    }

    #[cfg(not(windows))]
    {
        let _ = (&generated, config_path);
        println!("Full install is only implemented on Windows.");
    }

    Ok(())
}

/// Undo `install --full`. Best-effort by design: an uninstall that fails
/// halfway through should still remove as much as it safely can rather than
/// stopping at the first error (matching how `install_firefox_trust`
/// already treats per-target failures as non-fatal).
fn uninstall_full() -> anyhow::Result<()> {
    #[cfg(windows)]
    {
        match agent::service_install::uninstall() {
            Ok(()) => println!(
                "Stopped and removed the '{}' Windows Service.",
                agent::SERVICE_DISPLAY_NAME
            ),
            Err(err) => println!(
                "Could not remove the Windows Service ({err}); it may not be installed, or this \
                 process isn't elevated."
            ),
        }

        match agent_ca::remove_root_cert(agent_ca::COMMON_NAME, agent_ca::StoreScope::LocalMachine) {
            Ok(count) if count > 0 => println!(
                "Removed {count} CA certificate(s) from the Local Machine Trusted Root store."
            ),
            Ok(_) => println!(
                "No matching CA certificate found in the Local Machine Trusted Root store (already \
                 removed, or still cached elsewhere and Windows is holding onto it)."
            ),
            Err(err) => println!("Could not remove the CA certificate ({err})."),
        }

        println!(
            "Note: any user who ran `enable-proxy` should run `agentctl disable-proxy` themselves \
             first - per-user browser proxy settings aren't touched by an elevated uninstall."
        );
    }

    #[cfg(not(windows))]
    {
        println!("Uninstall is only implemented on Windows.");
    }

    Ok(())
}

fn status(config: &AgentConfig) -> anyhow::Result<()> {
    println!("Config:");
    println!("  proxy:  {}:{}", config.proxy.listen_addr, config.proxy.listen_port);
    println!("  ca cert: {} (exists: {})", config.ca.cert_path.display(), config.ca.cert_path.exists());
    println!("  ca key:  {} (exists: {})", config.ca.key_path.display(), config.ca.key_path.exists());
    println!("  policy:  {} (exists: {})", config.policy.source.display(), config.policy.source.exists());
    println!("  target domains: {:?}", config.targets.domains);
    Ok(())
}
