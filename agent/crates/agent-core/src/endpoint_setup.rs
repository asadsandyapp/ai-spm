//! Endpoint-level setup for routing browser traffic through the local agent.
//!
//! This is best-effort: managed installers should run the agent with enough
//! privileges to install the CA and configure OS proxy settings. Local dev runs
//! still benefit from user-level GNOME proxy and NSS trust-store updates.

use std::env;
use std::fs;
use std::net::SocketAddr;
use std::path::{Path, PathBuf};
use std::process::Command;

use thiserror::Error;
use tracing::{debug, info, warn};

use crate::config::Config;
use crate::network_setup::{block_quic, configure_network_redirect};
use crate::proxy::CaAuthority;

#[derive(Debug, Error)]
pub enum EndpointSetupError {
    #[error("MITM CA generation failed: {0}")]
    CaGeneration(#[from] crate::proxy::CaError),
}

#[derive(Debug, Default)]
pub struct EndpointSetupReport {
    pub ca_ready: bool,
    pub system_ca_installed: bool,
    pub nss_ca_installed: bool,
    pub proxy_configured: bool,
    pub network_redirect_configured: bool,
    pub quic_blocked: bool,
}

/// Generate/trust the MITM CA and configure supported OS proxy settings.
pub fn configure_endpoint(config: &Config) -> Result<EndpointSetupReport, EndpointSetupError> {
    if !config.auto_configure_endpoint {
        info!("endpoint auto-configuration disabled");
        return Ok(EndpointSetupReport::default());
    }

    let ca = CaAuthority::load_or_create(&config.mitm_ca_dir())?;
    let ca_cert_path = ca.ca_cert_path();
    let mut report = EndpointSetupReport {
        ca_ready: true,
        ..EndpointSetupReport::default()
    };

    if config.auto_install_ca {
        report.system_ca_installed = install_system_ca(&ca_cert_path);
        report.nss_ca_installed = install_nss_ca(&ca_cert_path);
    } else {
        info!("MITM CA auto-install disabled");
    }

    if config.auto_configure_proxy {
        report.proxy_configured = configure_system_proxy(config.proxy_listen);
    } else {
        info!("explicit browser proxy auto-configuration disabled (transparent mode)");
    }

    if config.auto_configure_network && config.transparent_enabled {
        let service_uid = service_uid_for_network_setup();
        report.network_redirect_configured = configure_network_redirect(
            config.transparent_listen.port(),
            config.socket_mark,
            service_uid,
        );
        report.quic_blocked = block_quic();
    } else if config.transparent_enabled {
        info!("network redirect auto-configuration disabled");
    }

    info!(
        ca_ready = report.ca_ready,
        system_ca_installed = report.system_ca_installed,
        nss_ca_installed = report.nss_ca_installed,
        proxy_configured = report.proxy_configured,
        network_redirect_configured = report.network_redirect_configured,
        quic_blocked = report.quic_blocked,
        "endpoint auto-configuration complete"
    );

    Ok(report)
}

#[cfg(target_os = "linux")]
fn install_system_ca(ca_cert_path: &Path) -> bool {
    if !command_exists("update-ca-certificates") {
        debug!("update-ca-certificates not found; skipping system CA store");
        return false;
    }

    let target = Path::new("/usr/local/share/ca-certificates/ai-spm-mitm.crt");
    if let Err(err) = fs::copy(ca_cert_path, target) {
        warn!(
            source = %ca_cert_path.display(),
            target = %target.display(),
            error = %err,
            "could not install MITM CA into system store; run agent as root or install through MDM/GPO"
        );
        return false;
    }

    match Command::new("update-ca-certificates").status() {
        Ok(status) if status.success() => {
            info!(target = %target.display(), "MITM CA installed into system trust store");
            true
        }
        Ok(status) => {
            warn!(status = %status, "update-ca-certificates failed");
            false
        }
        Err(err) => {
            warn!(error = %err, "failed to run update-ca-certificates");
            false
        }
    }
}

#[cfg(not(target_os = "linux"))]
fn install_system_ca(_ca_cert_path: &Path) -> bool {
    warn!("automatic system CA installation is not implemented for this OS");
    false
}

#[cfg(target_os = "linux")]
fn install_nss_ca(ca_cert_path: &Path) -> bool {
    if !command_exists("certutil") {
        debug!("certutil not found; skipping NSS browser trust stores");
        return false;
    }

    let mut installed = false;
    for db in nss_databases() {
        if install_ca_into_nss_db(&db, ca_cert_path) {
            installed = true;
        }
    }

    if !installed {
        debug!("no writable NSS trust stores found");
    }
    installed
}

#[cfg(not(target_os = "linux"))]
fn install_nss_ca(_ca_cert_path: &Path) -> bool {
    false
}

#[cfg(target_os = "linux")]
fn configure_system_proxy(listen: SocketAddr) -> bool {
    if !command_exists("gsettings") {
        warn!("gsettings not found; automatic desktop proxy setup is unavailable");
        return false;
    }

    let host = listen.ip().to_string();
    let port = listen.port().to_string();
    let commands = [
        ["set", "org.gnome.system.proxy", "mode", "manual"],
        ["set", "org.gnome.system.proxy.http", "host", host.as_str()],
        ["set", "org.gnome.system.proxy.http", "port", port.as_str()],
        ["set", "org.gnome.system.proxy.https", "host", host.as_str()],
        ["set", "org.gnome.system.proxy.https", "port", port.as_str()],
        [
            "set",
            "org.gnome.system.proxy",
            "ignore-hosts",
            "['localhost', '127.0.0.0/8', '::1']",
        ],
    ];

    let mut ok = true;
    for args in commands {
        match Command::new("gsettings").args(args).status() {
            Ok(status) if status.success() => {}
            Ok(status) => {
                warn!(?args, status = %status, "gsettings proxy command failed");
                ok = false;
            }
            Err(err) => {
                warn!(?args, error = %err, "failed to run gsettings proxy command");
                ok = false;
            }
        }
    }

    if ok {
        info!(%listen, "system proxy configured to route traffic through AI-SPM agent");
    }
    ok
}

#[cfg(not(target_os = "linux"))]
fn configure_system_proxy(_listen: SocketAddr) -> bool {
    warn!("automatic system proxy configuration is not implemented for this OS");
    false
}

#[cfg(target_os = "linux")]
fn nss_databases() -> Vec<PathBuf> {
    let mut dbs = Vec::new();
    let Some(home) = env::var_os("HOME").map(PathBuf::from) else {
        return dbs;
    };

    let chrome_db = home.join(".pki/nssdb");
    if chrome_db.join("cert9.db").exists() || chrome_db.join("cert8.db").exists() {
        dbs.push(chrome_db);
    }

    let firefox_root = home.join(".mozilla/firefox");
    if let Ok(entries) = fs::read_dir(firefox_root) {
        for entry in entries.flatten() {
            let path = entry.path();
            if path.is_dir() && (path.join("cert9.db").exists() || path.join("cert8.db").exists()) {
                dbs.push(path);
            }
        }
    }

    dbs
}

#[cfg(target_os = "linux")]
fn install_ca_into_nss_db(db: &Path, ca_cert_path: &Path) -> bool {
    let db_arg = format!("sql:{}", db.display());
    let _ = Command::new("certutil")
        .args(["-d", &db_arg, "-D", "-n", "AI-SPM MITM CA"])
        .status();

    match Command::new("certutil")
        .args([
            "-d",
            &db_arg,
            "-A",
            "-t",
            "C,,",
            "-n",
            "AI-SPM MITM CA",
            "-i",
        ])
        .arg(ca_cert_path)
        .status()
    {
        Ok(status) if status.success() => {
            info!(db = %db.display(), "MITM CA installed into NSS trust store");
            true
        }
        Ok(status) => {
            warn!(db = %db.display(), status = %status, "certutil failed for NSS trust store");
            false
        }
        Err(err) => {
            warn!(db = %db.display(), error = %err, "failed to run certutil");
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

#[cfg(unix)]
fn service_uid_for_network_setup() -> Option<u32> {
    if let Ok(value) = std::env::var("AISPM_SERVICE_UID") {
        if let Ok(uid) = value.parse() {
            return Some(uid);
        }
    }
    Some(unsafe { libc::getuid() })
}

#[cfg(not(unix))]
fn service_uid_for_network_setup() -> Option<u32> {
    None
}
