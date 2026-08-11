//! Local “admin disabled protection” latch.
//!
//! When the gateway reports the agent was revoked (403) or deleted (404), we
//! write a flag under `/etc/ai-spm` so:
//! - heartbeat does not re-register
//! - agent startup skips MITM / registration
//! - mitmproxy addon skips PII masking while the flag exists
//!
//! Cleared on reinstall (`install-agent.sh`).

use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;

use tracing::{info, warn};

use crate::gateway::GatewayClient;
use crate::network_setup::{remove_network_redirect, unblock_quic};

pub const PROTECTION_DISABLED_FLAG: &str = "protection-disabled";

pub fn state_dir() -> PathBuf {
    PathBuf::from(
        std::env::var("AISPM_STATE_DIR").unwrap_or_else(|_| "/etc/ai-spm".to_string()),
    )
}

pub fn flag_path() -> PathBuf {
    state_dir().join(PROTECTION_DISABLED_FLAG)
}

pub fn is_protection_disabled() -> bool {
    flag_path().is_file()
}

/// Persist admin-disable latch and tear down local interception best-effort.
pub fn enter_protection_disabled(gateway: &GatewayClient, reason: &str) {
    let path = flag_path();
    if let Some(parent) = path.parent() {
        let _ = fs::create_dir_all(parent);
    }
    match fs::write(
        &path,
        format!(
            "disabled_at={}\nreason={}\n",
            chrono_like_now(),
            reason
        ),
    ) {
        Ok(()) => info!(path = %path.display(), reason, "protection disabled by gateway admin action"),
        Err(err) => warn!(
            error = %err,
            path = %path.display(),
            "failed to write protection-disabled flag (masking may continue until uninstall)"
        ),
    }

    gateway.clear_agent_id();
    scrub_agent_id_from_env();

    if remove_network_redirect() {
        info!("removed transparent iptables redirect after admin disable");
    } else {
        warn!("could not remove iptables redirect (need root / helper); API MITM may still receive traffic");
    }
    let _ = unblock_quic();

    stop_web_mitm_best_effort();
}

fn chrono_like_now() -> String {
    use std::time::{SystemTime, UNIX_EPOCH};
    let secs = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_secs())
        .unwrap_or(0);
    secs.to_string()
}

fn scrub_agent_id_from_env() {
    let env_path = PathBuf::from(
        std::env::var("AISPM_ENV_FILE").unwrap_or_else(|_| "/etc/ai-spm/agent.env".to_string()),
    );
    if !env_path.is_file() {
        return;
    }
    let Ok(contents) = fs::read_to_string(&env_path) else {
        return;
    };
    let mut changed = false;
    let mut out = String::new();
    for line in contents.lines() {
        if line.starts_with("AISPM_AGENT_ID=") {
            changed = true;
            continue;
        }
        out.push_str(line);
        out.push('\n');
    }
    if changed {
        if let Err(err) = fs::write(&env_path, out) {
            warn!(error = %err, "failed to scrub AISPM_AGENT_ID from env file");
        }
    }
}

fn stop_web_mitm_best_effort() {
    // Web UI masking lives in mitmproxy; stopping the unit ends masking immediately.
    for args in [
        vec!["stop", "ai-spm-web-mitm"],
        vec!["--user", "stop", "ai-spm-web-mitm"],
    ] {
        match Command::new("systemctl").args(&args).output() {
            Ok(out) if out.status.success() => {
                info!(?args, "stopped web-mitm service after admin disable");
                return;
            }
            Ok(out) => {
                let stderr = String::from_utf8_lossy(&out.stderr);
                warn!(?args, stderr = %stderr.trim(), "systemctl stop web-mitm failed");
            }
            Err(err) => warn!(error = %err, "systemctl not available to stop web-mitm"),
        }
    }
    // Addon also honors the flag file even if the unit keeps running.
    if Path::new("/etc/ai-spm/protection-disabled").is_file() {
        info!("web-mitm addon will skip masking while protection-disabled flag is present");
    }
}

pub fn clear_protection_disabled() {
    let path = flag_path();
    if path.is_file() {
        match fs::remove_file(&path) {
            Ok(()) => info!(path = %path.display(), "cleared protection-disabled flag"),
            Err(err) => warn!(error = %err, "failed to clear protection-disabled flag"),
        }
    }
}
