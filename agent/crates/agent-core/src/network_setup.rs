//! Linux network redirect setup for transparent TLS interception.
//!
//! Installs iptables NAT rules that redirect outbound TCP/443 to the local
//! transparent interceptor. Agent-originated connections carry a socket mark and
//! are excluded so upstream relay does not loop.

use std::process::Command;

use tracing::{info, warn};

pub const IPTABLES_CHAIN: &str = "AISPM";
pub const IPTABLES_COMMENT: &str = "ai-spm-transparent";

/// Install OUTPUT redirect rules for transparent HTTPS interception.
#[cfg(target_os = "linux")]
pub fn configure_network_redirect(
    transparent_port: u16,
    socket_mark: u32,
    service_uid: Option<u32>,
) -> bool {
    if !command_exists("iptables") {
        warn!("iptables not found; transparent interception requires manual firewall setup");
        return false;
    }

    remove_network_redirect();

    let mark_hex = format!("0x{socket_mark:x}");
    let mut ok = true;

    ok &= run_iptables(&["-t", "nat", "-N", IPTABLES_CHAIN])
        || run_iptables(&["-t", "nat", "-F", IPTABLES_CHAIN]);

    // Agent process outbound connections must bypass redirect. The service user
    // cannot always set SO_MARK (EPERM), so uid-owner exclusion is primary.
    if let Some(uid) = service_uid {
        let uid_str = uid.to_string();
        ok &= run_iptables(&[
            "-t",
            "nat",
            "-A",
            IPTABLES_CHAIN,
            "-m",
            "owner",
            "--uid-owner",
            &uid_str,
            "-j",
            "RETURN",
        ]);
    }

    // Best-effort secondary exclusion for marked upstream sockets.
    ok &= run_iptables(&[
        "-t",
        "nat",
        "-A",
        IPTABLES_CHAIN,
        "-m",
        "mark",
        "--mark",
        &mark_hex,
        "-j",
        "RETURN",
    ]);

    // Never redirect loopback or link-local traffic.
    ok &= run_iptables(&[
        "-t",
        "nat",
        "-A",
        IPTABLES_CHAIN,
        "-d",
        "127.0.0.0/8",
        "-j",
        "RETURN",
    ]);
    ok &= run_iptables(&[
        "-t",
        "nat",
        "-A",
        IPTABLES_CHAIN,
        "-d",
        "169.254.0.0/16",
        "-j",
        "RETURN",
    ]);

    ok &= run_iptables(&[
        "-t",
        "nat",
        "-A",
        IPTABLES_CHAIN,
        "-p",
        "tcp",
        "--dport",
        "443",
        "-m",
        "comment",
        "--comment",
        IPTABLES_COMMENT,
        "-j",
        "REDIRECT",
        "--to-ports",
        &transparent_port.to_string(),
    ]);

    if !run_iptables(&["-t", "nat", "-C", "OUTPUT", "-j", IPTABLES_CHAIN]) {
        ok &= run_iptables(&["-t", "nat", "-I", "OUTPUT", "1", "-j", IPTABLES_CHAIN]);
    }

    if ok {
        info!(
            transparent_port,
            socket_mark = mark_hex,
            "iptables transparent HTTPS redirect installed"
        );
    } else {
        warn!("iptables transparent redirect installation failed");
    }
    ok
}

/// Remove AI-SPM iptables redirect rules.
#[cfg(target_os = "linux")]
pub fn remove_network_redirect() -> bool {
    if !command_exists("iptables") {
        return false;
    }

    while run_iptables(&["-t", "nat", "-D", "OUTPUT", "-j", IPTABLES_CHAIN]) {}

    let _ = run_iptables(&["-t", "nat", "-F", IPTABLES_CHAIN]);
    let _ = run_iptables(&["-t", "nat", "-X", IPTABLES_CHAIN]);

    info!("iptables transparent HTTPS redirect removed");
    true
}

#[cfg(not(target_os = "linux"))]
pub fn configure_network_redirect(
    _transparent_port: u16,
    _socket_mark: u32,
    _service_uid: Option<u32>,
) -> bool {
    warn!("transparent network redirect is only implemented on Linux");
    false
}

#[cfg(not(target_os = "linux"))]
pub fn remove_network_redirect() -> bool {
    false
}

/// Block outbound QUIC (UDP/443) so clients fall back to TCP through redirect.
#[cfg(target_os = "linux")]
pub fn block_quic() -> bool {
    if !command_exists("iptables") {
        return false;
    }
    let comment = "ai-spm-quic-block";
    if !run_iptables(&[
        "-C",
        "OUTPUT",
        "-p",
        "udp",
        "--dport",
        "443",
        "-m",
        "comment",
        "--comment",
        comment,
        "-j",
        "REJECT",
    ]) {
        let _ = run_iptables(&[
            "-A",
            "OUTPUT",
            "-p",
            "udp",
            "--dport",
            "443",
            "-m",
            "comment",
            "--comment",
            comment,
            "-j",
            "REJECT",
        ]);
    }
    if command_exists("ip6tables") {
        let _ = run_ip6tables(&[
            "-A",
            "OUTPUT",
            "-p",
            "udp",
            "--dport",
            "443",
            "-m",
            "comment",
            "--comment",
            comment,
            "-j",
            "REJECT",
        ]);
    }
    info!("outbound QUIC (UDP/443) blocked — clients use TCP through transparent redirect");
    true
}

#[cfg(not(target_os = "linux"))]
pub fn block_quic() -> bool {
    false
}

#[cfg(target_os = "linux")]
pub fn unblock_quic() -> bool {
    let comment = "ai-spm-quic-block";
    while run_iptables(&[
        "-D",
        "OUTPUT",
        "-p",
        "udp",
        "--dport",
        "443",
        "-m",
        "comment",
        "--comment",
        comment,
        "-j",
        "REJECT",
    ]) {}
    if command_exists("ip6tables") {
        while run_ip6tables(&[
            "-D",
            "OUTPUT",
            "-p",
            "udp",
            "--dport",
            "443",
            "-m",
            "comment",
            "--comment",
            comment,
            "-j",
            "REJECT",
        ]) {}
    }
    true
}

#[cfg(not(target_os = "linux"))]
pub fn unblock_quic() -> bool {
    false
}

#[cfg(target_os = "linux")]
fn run_iptables(args: &[&str]) -> bool {
    match Command::new("iptables").args(args).status() {
        Ok(status) => status.success(),
        Err(err) => {
            warn!(?args, error = %err, "failed to run iptables");
            false
        }
    }
}

#[cfg(target_os = "linux")]
fn run_ip6tables(args: &[&str]) -> bool {
    match Command::new("ip6tables").args(args).status() {
        Ok(status) => status.success(),
        Err(err) => {
            warn!(?args, error = %err, "failed to run ip6tables");
            false
        }
    }
}

fn command_exists(command: &str) -> bool {
    Command::new("sh")
        .arg("-c")
        .arg(format!("command -v {command} >/dev/null 2>&1"))
        .status()
        .map(|status| status.success())
        .unwrap_or(false)
}
