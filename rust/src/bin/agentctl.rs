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
    /// Full production install: CA into the system-wide trust store,
    /// Firefox enterprise trust, and `agentd` registered as an auto-start
    /// background service (a Windows Service, or a systemd unit on Linux)
    /// with crash-restart recovery. Requires an elevated/root process. This
    /// is what the MSI/`.deb` installer runs - the granular subcommands
    /// above stay as they were for dev/test/troubleshooting.
    Install {
        /// Perform the full production install. Currently the only
        /// supported mode - the flag exists so the installer's invocation
        /// reads self-documenting and to leave room for a lighter-weight
        /// mode later without a breaking CLI change.
        #[arg(long)]
        full: bool,
    },
    /// Undo `install --full`: stop and remove the background service, and
    /// best-effort remove the system-wide CA certificate. Requires an
    /// elevated/root process. Per-user state from `enable-proxy` is
    /// untouched - each user should run `disable-proxy` themselves first.
    Uninstall,
    /// Register this agent with the AI-SPM control-plane using the `[cloud]`
    /// install token. `install --full` already attempts this once; use this
    /// to retry by hand (e.g. the backend was unreachable at install time)
    /// or to re-register from scratch after deleting `data/cloud/registration.json`.
    Register,
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
        Command::Register => register_cloud(&load_config(&cli.config)?),
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

    #[cfg(target_os = "linux")]
    {
        match agent_ca::install_root_cert(&generated.cert_pem, agent_ca::StoreScope::CurrentUser) {
            Ok(()) => println!(
                "Installed AI-SPM DLP Agent CA into your user NSS database (~/.pki/nssdb) - this covers \
                 Chrome/Chromium for your account. Certificate: {}\nFirefox trust and system-wide coverage \
                 need `agentctl install --full` (run as root).",
                config.ca.cert_path.display()
            ),
            Err(err) => println!(
                "Could not install into ~/.pki/nssdb ({err}). This usually means `certutil` isn't \
                 installed - run `sudo apt install libnss3-tools` and try again, or use `sudo agentctl \
                 install --full` for a system-wide install instead."
            ),
        }
    }

    #[cfg(not(any(windows, target_os = "linux")))]
    {
        let _ = &generated;
        println!(
            "CA generated at {}, but trust-store install is only implemented on Windows and Linux.",
            config.ca.cert_path.display()
        );
    }

    Ok(())
}

/// Firefox ignores the OS certificate stores, so `install_root_cert` above
/// has no effect on it. Set the `ImportEnterpriseRoots` enterprise policy on
/// every Firefox install found so it trusts the OS stores instead - see
/// `agent_ca::firefox` for why. Best-effort: a Firefox that isn't found or
/// can't be written to (machine-wide install, no admin) is reported but
/// doesn't fail the caller for everything else. Only called from the
/// elevated/root `install --full` path - on Linux, Firefox's system-wide
/// `policies.json` locations need root, so there's no equivalent call from
/// the no-root granular `install-ca` path (unlike Windows, where it's called
/// from both - see `install_ca` below).
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

    #[cfg(target_os = "linux")]
    {
        println!(
            "PAC written to {} and served at {} (start agentd if it isn't running).\n\
             Linux has no single system-wide proxy auto-config API, so this needs a manual, \
             per-desktop step - pick whichever applies to you:\n\
             \n\
             \x20 Firefox: Settings -> General -> Network Settings -> Settings... -> \"Automatic \
             proxy configuration URL\", paste the PAC URL above, OK.\n\
             \x20 GNOME (covers Chrome/Chromium and other GTK apps that follow the desktop proxy \
             setting): Settings -> Network -> Network Proxy -> Automatic, paste the PAC URL above.\n\
             \n\
             Then restart your browser. Only {:?} will route through the agent; everything else \
             stays DIRECT. Run `agentctl disable-proxy` for the steps to revert.",
            abs_path.display(),
            pac_url,
            config.targets.domains,
        );
    }

    #[cfg(not(any(windows, target_os = "linux")))]
    {
        let _ = &pac_url;
        println!(
            "PAC file written to {}, but system proxy configuration is only implemented on Windows and Linux.",
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

    #[cfg(target_os = "linux")]
    {
        println!(
            "Nothing to clear automatically on Linux - revert whichever manual step `enable-proxy` \
             had you do: Firefox -> Settings -> General -> Network Settings -> switch off \"Automatic \
             proxy configuration URL\"; GNOME -> Settings -> Network -> Network Proxy -> switch to \
             \"Off\". Then restart your browser."
        );
    }

    #[cfg(not(any(windows, target_os = "linux")))]
    {
        println!("System proxy configuration is only implemented on Windows and Linux; nothing to disable.");
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

    #[cfg(target_os = "linux")]
    {
        let _ = config_path; // the systemd unit already hardcodes its own config path
        agent_ca::install_root_cert(&generated.cert_pem, agent_ca::StoreScope::LocalMachine)
            .context("installing CA into the system trust store (this requires root)")?;
        println!("Installed AI-SPM DLP Agent CA into the system trust store (update-ca-certificates).");

        install_firefox_trust();

        // The service runs as the unprivileged `agent::SERVICE_USER`, not
        // root (see the `.service` file's User=/hardening directives) - but
        // everything generated above (the local MITM CA, its state dir) was
        // just written by *this* root process. Without this chown, the
        // service's very first start would fail to read its own CA key.
        chown_state_dirs(config).context("handing state/log directories to the service user")?;

        agent::systemd::install().context("enabling the ai-spm-dlp-agent systemd service")?;
        println!("Enabled and started the 'ai-spm-dlp-agent' systemd service (auto-start, restart on failure).");
        println!(
            "Each user still needs to run `agentctl enable-proxy` once (no root required) to point \
             their own browser at the agent."
        );
    }

    #[cfg(not(any(windows, target_os = "linux")))]
    {
        let _ = (&generated, config_path);
        println!("Full install is only implemented on Windows and Linux.");
    }

    if config.cloud.is_configured() {
        // Best-effort, matching `install_firefox_trust`'s tone above: a
        // backend that's unreachable right now must not fail the install -
        // `agentd`'s own startup retry (see `runtime.rs::register_with_retry`)
        // picks this up and keeps trying once the service is running.
        match register_cloud_once(config) {
            Ok(response) => println!(
                "Registered with the AI-SPM control-plane (agent_id: {}).",
                response.id
            ),
            Err(err) => println!(
                "Cloud registration failed ({err}); agentd will keep retrying in the background \
                 once it starts. Run `agentctl register` to retry by hand."
            ),
        }
    }

    Ok(())
}

/// Hands the CA/PAC state dir and the log dir to [`agent::SERVICE_USER`],
/// recursively, so the sandboxed systemd service (which runs as that user,
/// not root - see the `.service` file) can read the CA key this same
/// (root) process just generated, and write its own logs/PAC file. Derived
/// from `config` rather than hardcoding `/var/lib/ai-spm-dlp-agent` and
/// `/var/log/ai-spm-dlp-agent` directly, so a customized packaging config
/// doesn't silently leave the wrong directory root-owned.
#[cfg(target_os = "linux")]
fn chown_state_dirs(config: &AgentConfig) -> anyhow::Result<()> {
    let mut dirs = vec![config.logging.file_dir.clone()];
    if let Some(parent) = config.ca.cert_path.parent() {
        dirs.push(parent.to_path_buf());
    }
    if let Some(parent) = config.sysnet.pac_path.parent() {
        dirs.push(parent.to_path_buf());
    }

    for dir in dirs {
        if !dir.exists() {
            continue;
        }
        let owner = format!("{0}:{0}", agent::SERVICE_USER);
        let output = std::process::Command::new("chown")
            .args(["-R", &owner])
            .arg(&dir)
            .output()
            .with_context(|| format!("spawning chown for {}", dir.display()))?;
        anyhow::ensure!(
            output.status.success(),
            "chown -R {owner} {} failed: {}",
            dir.display(),
            String::from_utf8_lossy(&output.stderr).trim()
        );
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

    #[cfg(target_os = "linux")]
    {
        match agent::systemd::uninstall() {
            Ok(()) => println!("Stopped and disabled the 'ai-spm-dlp-agent' systemd service."),
            Err(err) => println!(
                "Could not disable the systemd service ({err}); it may not be installed, or this \
                 process isn't root."
            ),
        }

        match agent_ca::remove_root_cert(agent_ca::COMMON_NAME, agent_ca::StoreScope::LocalMachine) {
            Ok(count) if count > 0 => println!("Removed the CA certificate from the system trust store."),
            Ok(_) => println!(
                "No matching CA certificate found in the system trust store (already removed)."
            ),
            Err(err) => println!("Could not remove the CA certificate ({err})."),
        }

        println!(
            "Note: any user who ran `enable-proxy` should revert their manual browser proxy setting \
             themselves first - per-user settings aren't touched by an elevated uninstall."
        );
    }

    #[cfg(not(any(windows, target_os = "linux")))]
    {
        println!("Uninstall is only implemented on Windows and Linux.");
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

    if !config.cloud.is_configured() {
        println!("  cloud:   not configured (standalone mode)");
    } else {
        let state_path = config.cloud.state_dir.join("registration.json");
        match agent_core::registration::load_registration_state(&state_path) {
            Some(state) => println!(
                "  cloud:   registered (agent_id: {}, gateway: {})",
                state.agent_id,
                config.cloud.gateway_url.as_deref().unwrap_or("?"),
            ),
            None => println!(
                "  cloud:   configured but not yet registered (gateway: {}) - run `agentctl register`",
                config.cloud.gateway_url.as_deref().unwrap_or("?"),
            ),
        }
    }

    Ok(())
}

/// `agentctl register` - explicit manual trigger, for retrying after a
/// failed `install --full` attempt or re-registering by hand.
fn register_cloud(config: &AgentConfig) -> anyhow::Result<()> {
    anyhow::ensure!(
        config.cloud.is_configured(),
        "[cloud] is not configured (need both gateway_url and install_token) - nothing to register."
    );
    let response = register_cloud_once(config)?;
    println!(
        "Registered with the AI-SPM control-plane (agent_id: {}, org_id: {}).",
        response.id, response.org_id
    );
    Ok(())
}

/// Runs one `register_and_persist` attempt to completion. `agentctl`'s
/// `main()` is synchronous everywhere else (none of its other subcommands
/// need async I/O), so this spins up a throwaway single-threaded runtime
/// just for this one call rather than making the whole binary async.
fn register_cloud_once(config: &AgentConfig) -> anyhow::Result<agent_core::RegisterResponse> {
    let runtime = tokio::runtime::Builder::new_current_thread()
        .enable_all()
        .build()
        .context("building tokio runtime for cloud registration")?;
    runtime
        .block_on(agent_core::registration::register_and_persist(&config.cloud))
        .map_err(|err| anyhow::anyhow!(err))
}
