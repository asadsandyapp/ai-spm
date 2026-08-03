//! Installs the local root CA into Linux trust stores.
//!
//! Unlike Windows, there's no single API for this - it's done by shelling
//! out to the standard Debian/Ubuntu tooling:
//!
//! - [`StoreScope::LocalMachine`] writes the cert into
//!   `/usr/local/share/ca-certificates/` and runs `update-ca-certificates`,
//!   which rebuilds the system trust bundle. On Debian/Ubuntu this also
//!   covers Chrome/Chromium (not just OpenSSL-based tools) because their
//!   `libnss3` package ships a p11-kit trust module that bridges the system
//!   store into NSS. Requires root.
//! - [`StoreScope::CurrentUser`] installs into the invoking user's NSS
//!   database (`~/.pki/nssdb`, what Chrome reads per-user) via `certutil`,
//!   requiring no elevation but requiring `libnss3-tools` to be installed.

use std::io::Write;
use std::path::PathBuf;
use std::process::Command;

use crate::error::CaError;

const SYSTEM_CERT_PATH: &str = "/usr/local/share/ca-certificates/ai-spm-dlp-agent.crt";

/// Which Linux certificate store scope to install the CA into.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum StoreScope {
    /// The invoking user's NSS database (`~/.pki/nssdb`) - no elevation
    /// required, but only covers apps that read that NSS DB (Chrome/
    /// Chromium), not Firefox (see `crate::firefox` for that) and not
    /// OpenSSL-based CLI tools.
    CurrentUser,
    /// The system trust store (`update-ca-certificates`) - requires root,
    /// but covers every account on the machine and (via the NSS/p11-kit
    /// bridge, Debian/Ubuntu-specific) Chrome as well.
    LocalMachine,
}

/// Install `cert_pem` (a PEM-encoded X.509 certificate) into the trust store
/// at the given `scope`.
pub fn install_root_cert(cert_pem: &str, scope: StoreScope) -> Result<(), CaError> {
    match scope {
        StoreScope::LocalMachine => {
            std::fs::write(SYSTEM_CERT_PATH, cert_pem).map_err(|source| CaError::Write {
                path: PathBuf::from(SYSTEM_CERT_PATH),
                source,
            })?;
            run_command("update-ca-certificates", &[])
        }
        StoreScope::CurrentUser => {
            let nssdb = user_nssdb_arg()?;
            let tmp_path = write_temp_pem(cert_pem)?;
            let result = run_command(
                "certutil",
                &[
                    "-d",
                    &nssdb,
                    "-A",
                    "-t",
                    "C,,",
                    "-n",
                    crate::COMMON_NAME,
                    "-i",
                    tmp_path.to_str().expect("temp path is valid UTF-8"),
                ],
            );
            let _ = std::fs::remove_file(&tmp_path);
            result
        }
    }
}

/// Best-effort removal of the CA from `scope`'s trust store. Returns how many
/// were removed (0 or 1 - unlike Windows there's exactly one place this CA
/// could be installed per scope). A failure to remove (e.g. `certutil` not
/// installed, or the file was never there) is reported by the caller, not
/// treated as fatal here - matches the Windows `remove_root_cert` contract.
pub fn remove_root_cert(common_name: &str, scope: StoreScope) -> Result<usize, CaError> {
    match scope {
        StoreScope::LocalMachine => {
            let existed = std::path::Path::new(SYSTEM_CERT_PATH).exists();
            if existed {
                std::fs::remove_file(SYSTEM_CERT_PATH).map_err(|source| CaError::Write {
                    path: PathBuf::from(SYSTEM_CERT_PATH),
                    source,
                })?;
                run_command("update-ca-certificates", &["--fresh"])?;
                Ok(1)
            } else {
                Ok(0)
            }
        }
        StoreScope::CurrentUser => {
            let nssdb = user_nssdb_arg()?;
            run_command("certutil", &["-D", "-d", &nssdb, "-n", common_name])?;
            Ok(1)
        }
    }
}

fn user_nssdb_arg() -> Result<String, CaError> {
    let home = std::env::var("HOME").map_err(|_| CaError::Command {
        command: "certutil".to_string(),
        reason: "HOME environment variable is not set".to_string(),
    })?;
    Ok(format!("sql:{home}/.pki/nssdb"))
}

/// Writes `cert_pem` to a fresh file under the temp dir and returns its path.
/// Uses `create_new` (fails if the path already exists, symlink or not)
/// rather than `File::create` (which happily follows an existing symlink) -
/// a local attacker who pre-creates a symlink at this predictable,
/// PID-based path can no longer redirect the write to a file they control.
/// Permissions are set to owner-only at creation (`mode`), not via a
/// separate `chmod` afterward, so there's no window where the file exists
/// world-readable.
fn write_temp_pem(cert_pem: &str) -> Result<PathBuf, CaError> {
    use std::os::unix::fs::OpenOptionsExt;

    let path = std::env::temp_dir().join(format!("ai-spm-dlp-agent-ca-{}.pem", std::process::id()));
    let mut file = std::fs::OpenOptions::new()
        .write(true)
        .create_new(true)
        .mode(0o600)
        .open(&path)
        .map_err(|source| CaError::Write {
            path: path.clone(),
            source,
        })?;
    file.write_all(cert_pem.as_bytes())
        .map_err(|source| CaError::Write {
            path: path.clone(),
            source,
        })?;
    Ok(path)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::os::unix::fs::PermissionsExt;

    fn expected_temp_path() -> PathBuf {
        std::env::temp_dir().join(format!("ai-spm-dlp-agent-ca-{}.pem", std::process::id()))
    }

    // A single test, not two: both scenarios target the same PID-derived
    // path `write_temp_pem` always uses, and cargo runs tests in parallel
    // threads of one process (same PID) - two separate tests racing on that
    // path would be flaky. Sequential steps in one test avoids that.
    #[test]
    fn write_temp_pem_writes_owner_only_and_refuses_to_follow_a_symlink() {
        let path = expected_temp_path();
        let _ = std::fs::remove_file(&path);

        // Happy path: no pre-existing file, and the result is owner-only.
        let written = write_temp_pem("hello").unwrap();
        assert_eq!(written, path);
        assert_eq!(std::fs::read_to_string(&path).unwrap(), "hello");
        let mode = std::fs::metadata(&path).unwrap().permissions().mode() & 0o777;
        assert_eq!(mode, 0o600);
        std::fs::remove_file(&path).unwrap();

        // A local attacker pre-creating a symlink at this predictable path
        // must not get their target written to - create_new fails on any
        // existing directory entry, symlink included, rather than following it.
        let decoy = std::env::temp_dir().join(format!("ai-spm-dlp-agent-ca-decoy-{}", std::process::id()));
        std::fs::write(&decoy, "attacker-controlled").unwrap();
        std::os::unix::fs::symlink(&decoy, &path).unwrap();

        let result = write_temp_pem("should not be written");
        assert!(result.is_err(), "expected write_temp_pem to refuse an existing symlink");
        assert_eq!(std::fs::read_to_string(&decoy).unwrap(), "attacker-controlled");

        std::fs::remove_file(&path).unwrap();
        std::fs::remove_file(&decoy).unwrap();
    }
}

fn run_command(program: &str, args: &[&str]) -> Result<(), CaError> {
    let output = Command::new(program)
        .args(args)
        .output()
        .map_err(|source| CaError::Command {
            command: program.to_string(),
            reason: format!("failed to spawn: {source}"),
        })?;

    if !output.status.success() {
        return Err(CaError::Command {
            command: program.to_string(),
            reason: format!(
                "exited with {}: {}",
                output.status,
                String::from_utf8_lossy(&output.stderr).trim()
            ),
        });
    }

    Ok(())
}
