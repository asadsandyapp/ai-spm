//! Firefox trust setup via the enterprise policy engine.
//!
//! Firefox ignores the Windows certificate stores by default (it ships its
//! own NSS trust store), so installing our CA into `CERT_SYSTEM_STORE_*`
//! (see [`crate::winstore`]) has no effect on it. Rather than writing
//! directly into Firefox's NSS `cert9.db` - an undocumented SQLite format
//! that varies across Firefox versions - we drop a `policies.json` enabling
//! `Certificates.ImportEnterpriseRoots`, a policy Firefox has supported
//! since version 65 specifically for this: it makes Firefox additionally
//! trust whatever the OS Root/CA certificate stores trust, which already
//! includes this agent's CA once `install_root_cert` has run.
//!
//! Firefox only reads `policies.json` from an install's own `distribution`
//! folder, not from a per-user profile directory, so this still needs a
//! writable install directory. The modern per-user install location
//! (`%LOCALAPPDATA%\Mozilla Firefox`) needs no elevation; the machine-wide
//! `Program Files` locations do.

use std::path::{Path, PathBuf};

use serde_json::{json, Value};

use crate::error::CaError;

/// Return every Firefox installation directory found on this machine.
///
/// Checks the per-user install location first (writable without admin),
/// then the two machine-wide `Program Files` locations. Installs that were
/// never registered with Windows (e.g. an extracted zip) aren't found -
/// this only covers the standard installer layouts.
#[cfg(windows)]
pub fn find_install_dirs() -> Vec<PathBuf> {
    let mut candidates = Vec::new();

    if let Ok(local_appdata) = std::env::var("LOCALAPPDATA") {
        candidates.push(PathBuf::from(local_appdata).join("Mozilla Firefox"));
    }
    if let Ok(program_files) = std::env::var("ProgramFiles") {
        candidates.push(PathBuf::from(program_files).join("Mozilla Firefox"));
    }
    if let Ok(program_files_x86) = std::env::var("ProgramFiles(x86)") {
        candidates.push(PathBuf::from(program_files_x86).join("Mozilla Firefox"));
    }

    candidates
        .into_iter()
        .filter(|dir| dir.join("firefox.exe").is_file())
        .collect()
}

/// Return every Firefox installation directory found on this machine.
///
/// Checks the standard Debian/Ubuntu package install locations, plus
/// whatever `firefox` resolves to on `PATH` (covers non-standard installs).
/// A Flatpak/Snap Firefox is sandboxed and doesn't read `distribution/
/// policies.json` the same way, so it isn't covered here.
#[cfg(target_os = "linux")]
pub fn find_install_dirs() -> Vec<PathBuf> {
    let mut candidates = vec![
        PathBuf::from("/usr/lib/firefox"),
        PathBuf::from("/usr/lib64/firefox"),
        PathBuf::from("/opt/firefox"),
    ];

    if let Ok(output) = std::process::Command::new("which").arg("firefox").output() {
        if output.status.success() {
            let path = String::from_utf8_lossy(&output.stdout).trim().to_string();
            if let Ok(resolved) = std::fs::canonicalize(&path) {
                if let Some(dir) = resolved.parent() {
                    candidates.push(dir.to_path_buf());
                }
            }
        }
    }

    candidates
        .into_iter()
        .filter(|dir| dir.join("firefox").is_file())
        .collect()
}

/// Merge the `ImportEnterpriseRoots` policy into
/// `<install_dir>/distribution/policies.json`, preserving any other
/// policies already configured there. Returns the path written.
///
/// Fails (permission denied) if `install_dir` is a machine-wide location and
/// the process isn't elevated - that's expected and left for the caller to
/// report, not retried or silently swallowed here.
pub fn install_enterprise_policy(install_dir: &Path) -> Result<PathBuf, CaError> {
    let policies_path = install_dir.join("distribution").join("policies.json");

    let mut root: Value = if policies_path.exists() {
        let text = std::fs::read_to_string(&policies_path).map_err(|source| CaError::Read {
            path: policies_path.clone(),
            source,
        })?;
        serde_json::from_str(&text)?
    } else {
        json!({})
    };

    if !root.is_object() {
        root = json!({});
    }
    let policies = root
        .as_object_mut()
        .expect("just ensured root is an object")
        .entry("policies")
        .or_insert_with(|| json!({}));
    if !policies.is_object() {
        *policies = json!({});
    }
    let certificates = policies
        .as_object_mut()
        .expect("just ensured policies is an object")
        .entry("Certificates")
        .or_insert_with(|| json!({}));
    if !certificates.is_object() {
        *certificates = json!({});
    }
    certificates
        .as_object_mut()
        .expect("just ensured certificates is an object")
        .insert("ImportEnterpriseRoots".to_string(), json!(true));

    if let Some(parent) = policies_path.parent() {
        std::fs::create_dir_all(parent).map_err(|source| CaError::CreateDir {
            path: parent.to_path_buf(),
            source,
        })?;
    }
    let pretty = serde_json::to_string_pretty(&root)?;
    std::fs::write(&policies_path, pretty).map_err(|source| CaError::Write {
        path: policies_path.clone(),
        source,
    })?;

    Ok(policies_path)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn temp_dir(name: &str) -> PathBuf {
        let dir = std::env::temp_dir().join(format!("agent-ca-firefox-test-{name}-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&dir);
        std::fs::create_dir_all(&dir).unwrap();
        dir
    }

    #[test]
    fn writes_fresh_policies_file() {
        let dir = temp_dir("fresh");
        let path = install_enterprise_policy(&dir).unwrap();

        let written: Value = serde_json::from_str(&std::fs::read_to_string(&path).unwrap()).unwrap();
        assert_eq!(written["policies"]["Certificates"]["ImportEnterpriseRoots"], json!(true));

        std::fs::remove_dir_all(&dir).unwrap();
    }

    #[test]
    fn preserves_existing_policies_when_merging() {
        let dir = temp_dir("merge");
        let distribution = dir.join("distribution");
        std::fs::create_dir_all(&distribution).unwrap();
        std::fs::write(
            distribution.join("policies.json"),
            r#"{"policies":{"DisableAppUpdate":true,"Certificates":{"Install":["custom.pem"]}}}"#,
        )
        .unwrap();

        let path = install_enterprise_policy(&dir).unwrap();
        let written: Value = serde_json::from_str(&std::fs::read_to_string(&path).unwrap()).unwrap();

        assert_eq!(written["policies"]["DisableAppUpdate"], json!(true));
        assert_eq!(written["policies"]["Certificates"]["Install"], json!(["custom.pem"]));
        assert_eq!(written["policies"]["Certificates"]["ImportEnterpriseRoots"], json!(true));

        std::fs::remove_dir_all(&dir).unwrap();
    }
}
