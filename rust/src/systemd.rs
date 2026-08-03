//! systemd integration for `agentd`. Used by `agentctl install --full` /
//! `agentctl uninstall`. Much thinner than the Windows Service equivalent
//! (`service_install.rs`) because there's no SCM-style dispatch protocol to
//! implement: the unit file itself (shipped by the `.deb`, see
//! `packaging/linux/ai-spm-dlp-agent.service`) already hardcodes the binary
//! path and config path, and systemd runs `agentd` as a plain foreground
//! process - all this module does is tell systemd about it.

use std::process::Command;

/// Reload unit files, enable the service (auto-start on boot from now on),
/// and (re)start it. Uses `restart` rather than `enable --now` so an
/// in-place package upgrade actually picks up the newly-installed binary
/// instead of leaving the old one running until a manual restart. Requires
/// root.
pub fn install() -> anyhow::Result<()> {
    run("systemctl", &["daemon-reload"])?;
    run("systemctl", &["enable", crate::SYSTEMD_UNIT_NAME])?;
    run("systemctl", &["restart", crate::SYSTEMD_UNIT_NAME])
}

/// Stop and disable the service. Requires root.
pub fn uninstall() -> anyhow::Result<()> {
    run("systemctl", &["disable", "--now", crate::SYSTEMD_UNIT_NAME])
}

fn run(program: &str, args: &[&str]) -> anyhow::Result<()> {
    let output = Command::new(program)
        .args(args)
        .output()
        .map_err(|e| anyhow::anyhow!("failed to spawn `{program}`: {e}"))?;

    anyhow::ensure!(
        output.status.success(),
        "`{program} {}` exited with {}: {}",
        args.join(" "),
        output.status,
        String::from_utf8_lossy(&output.stderr).trim()
    );

    Ok(())
}
