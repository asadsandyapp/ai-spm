use std::path::Path;

use rcgen::{BasicConstraints, CertificateParams, DistinguishedName, DnType, IsCa, Issuer, KeyPair, KeyUsagePurpose};
use time::{Duration, OffsetDateTime};

use crate::error::CaError;

/// A loaded (or freshly generated) local root CA: an `Issuer` ready to hand
/// to hudsucker's `RcgenAuthority` for signing per-host leaf certs, plus the
/// DER bytes of a self-signed root certificate suitable for installing into
/// the Windows trust store.
pub struct GeneratedCa {
    pub issuer: Issuer<'static, KeyPair>,
    pub cert_der: Vec<u8>,
    pub cert_pem: String,
}

/// The CA's subject common name - exposed so callers that need to identify
/// "our" cert among others in a Windows store (e.g. `agentctl uninstall`,
/// via [`crate::remove_root_cert`]) don't have to hardcode it a second time.
pub const COMMON_NAME: &str = "AI-SPM DLP Agent Local CA";
const ORG_NAME: &str = "AI-SPM";

/// The current subject, as a stable marker string. Compared against
/// `subject_marker_path`'s contents to detect a stale on-disk `root.crt`
/// left over from before `COMMON_NAME`/`ORG_NAME` last changed (this has
/// happened once already, during the BlockApt -> AI-SPM rename, and broke
/// browser trust because the installed cert's subject no longer matched
/// what freshly-signed leaf certs claimed to be issued by).
fn current_subject_marker() -> String {
    format!("{COMMON_NAME}|{ORG_NAME}")
}

/// Sidecar file recording which subject `cert_path` was generated with.
/// Kept as a plain marker file rather than re-parsing `cert_path`'s DER back
/// into a subject (which would pull in an X.509 parser just to read back a
/// string this same code wrote).
fn subject_marker_path(cert_path: &Path) -> std::path::PathBuf {
    cert_path.with_extension("subject")
}

/// Load a previously generated CA key from `key_path`, or generate a new one
/// and persist it there. The on-disk root certificate at `cert_path` is
/// (re)written whenever it's missing or was generated under a different
/// `COMMON_NAME`/`ORG_NAME` than the current constants; otherwise it's left
/// alone. Either way, the in-memory `Issuer` used to sign leaf certs always
/// reflects the current subject: this is safe because leaf-cert verification
/// only depends on the CA's public key and subject name matching what's in
/// the trust store, not on the exact serial number or validity window of any
/// particular self-signed representation of it.
pub fn load_or_generate(cert_path: &Path, key_path: &Path) -> Result<GeneratedCa, CaError> {
    let key_pair = if key_path.exists() {
        let pem = std::fs::read_to_string(key_path).map_err(|source| CaError::Read {
            path: key_path.to_path_buf(),
            source,
        })?;
        KeyPair::from_pem(&pem)?
    } else {
        let key_pair = KeyPair::generate()?;
        if let Some(parent) = key_path.parent() {
            std::fs::create_dir_all(parent).map_err(|source| CaError::CreateDir {
                path: parent.to_path_buf(),
                source,
            })?;
        }
        std::fs::write(key_path, key_pair.serialize_pem()).map_err(|source| CaError::Write {
            path: key_path.to_path_buf(),
            source,
        })?;
        restrict_key_permissions(key_path)?;
        key_pair
    };

    let params = ca_params()?;
    let cert = params.self_signed(&key_pair)?;
    let cert_der = cert.der().to_vec();
    let cert_pem = cert.pem();

    let marker_path = subject_marker_path(cert_path);
    let marker = current_subject_marker();
    let on_disk_marker_matches = std::fs::read_to_string(&marker_path)
        .map(|existing| existing == marker)
        .unwrap_or(false);

    if !cert_path.exists() || !on_disk_marker_matches {
        if let Some(parent) = cert_path.parent() {
            std::fs::create_dir_all(parent).map_err(|source| CaError::CreateDir {
                path: parent.to_path_buf(),
                source,
            })?;
        }
        std::fs::write(cert_path, &cert_pem).map_err(|source| CaError::Write {
            path: cert_path.to_path_buf(),
            source,
        })?;
        std::fs::write(&marker_path, &marker).map_err(|source| CaError::Write {
            path: marker_path,
            source,
        })?;
    }

    // A second, independent CertificateParams for the long-lived Issuer
    // object itself (kept separate from the one consumed by self_signed
    // above, since CertificateParams isn't Clone in all versions).
    let issuer_params = ca_params()?;
    let issuer = Issuer::new(issuer_params, key_pair);

    Ok(GeneratedCa {
        issuer,
        cert_der,
        cert_pem,
    })
}

/// Lock the CA private key down to owner-only access right after writing it.
/// `std::fs::write` applies no permission restriction of its own (subject to
/// umask on Unix - typically 0644 - and inherited ACLs on Windows), and this
/// key is installed into the **system-wide** trust store (see
/// `agentctl install --full` -> `StoreScope::LocalMachine`): a world-readable
/// key on a machine with any other local account lets that account mint
/// certificates trusted machine-wide, fully defeating the interception
/// trust model.
#[cfg(unix)]
fn restrict_key_permissions(path: &Path) -> Result<(), CaError> {
    use std::os::unix::fs::PermissionsExt;
    std::fs::set_permissions(path, std::fs::Permissions::from_mode(0o600)).map_err(|source| {
        CaError::Permissions {
            path: path.to_path_buf(),
            reason: source.to_string(),
        }
    })
}

/// Windows equivalent: strip inherited ACEs and grant access only to SYSTEM
/// (by well-known SID `*S-1-5-18`, not a localized name) and whichever
/// account is actually running this process. That second grant matters as
/// much as the first: this code runs both as LocalSystem (the Windows
/// Service, via `agentctl install --full`) and as the interactive user
/// (`agentctl install-ca`, or any dev/manual run) - locking the file to
/// "SYSTEM + Administrators" instead would deny the very account that just
/// created it, since group membership alone doesn't grant an elevated
/// token's access (this was caught by `reuses_key_and_leaves_cert_alone_*`
/// failing with Access Denied on the very next read).
#[cfg(windows)]
fn restrict_key_permissions(path: &Path) -> Result<(), CaError> {
    let whoami_output = std::process::Command::new("whoami").output().map_err(|source| {
        CaError::Permissions {
            path: path.to_path_buf(),
            reason: format!("failed to run whoami: {source}"),
        }
    })?;
    let current_user = String::from_utf8_lossy(&whoami_output.stdout).trim().to_string();

    let mut args = vec!["/inheritance:r".to_string(), "/grant:r".to_string(), "*S-1-5-18:F".to_string()];
    if !current_user.is_empty() {
        args.push(format!("{current_user}:F"));
    }

    let output = std::process::Command::new("icacls")
        .arg(path)
        .args(&args)
        .output()
        .map_err(|source| CaError::Permissions {
            path: path.to_path_buf(),
            reason: format!("failed to spawn icacls: {source}"),
        })?;

    if !output.status.success() {
        return Err(CaError::Permissions {
            path: path.to_path_buf(),
            reason: format!(
                "icacls exited with {}: {}",
                output.status,
                String::from_utf8_lossy(&output.stderr).trim()
            ),
        });
    }
    Ok(())
}

#[cfg(not(any(unix, windows)))]
fn restrict_key_permissions(_path: &Path) -> Result<(), CaError> {
    Ok(())
}

fn ca_params() -> Result<CertificateParams, CaError> {
    let mut params = CertificateParams::new(Vec::<String>::new())?;
    params.is_ca = IsCa::Ca(BasicConstraints::Constrained(0));
    params.key_usages = vec![KeyUsagePurpose::KeyCertSign, KeyUsagePurpose::CrlSign];

    let mut dn = DistinguishedName::new();
    dn.push(DnType::CommonName, COMMON_NAME);
    dn.push(DnType::OrganizationName, ORG_NAME);
    params.distinguished_name = dn;

    let now = OffsetDateTime::now_utc();
    params.not_before = now - Duration::days(1);
    params.not_after = now + Duration::days(3650);

    Ok(params)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn temp_dir(name: &str) -> std::path::PathBuf {
        let dir = std::env::temp_dir().join(format!("agent-ca-test-{name}-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&dir);
        std::fs::create_dir_all(&dir).unwrap();
        dir
    }

    #[cfg(unix)]
    #[test]
    fn generated_key_is_owner_only_readable() {
        use std::os::unix::fs::PermissionsExt;

        let dir = temp_dir("perms");
        let cert_path = dir.join("root.crt");
        let key_path = dir.join("root.key");

        load_or_generate(&cert_path, &key_path).unwrap();

        let mode = std::fs::metadata(&key_path).unwrap().permissions().mode() & 0o777;
        assert_eq!(mode, 0o600);

        std::fs::remove_dir_all(&dir).unwrap();
    }

    #[test]
    fn generates_cert_key_and_marker_on_first_run() {
        let dir = temp_dir("fresh");
        let cert_path = dir.join("root.crt");
        let key_path = dir.join("root.key");

        load_or_generate(&cert_path, &key_path).unwrap();

        assert!(cert_path.exists());
        assert!(key_path.exists());
        assert_eq!(
            std::fs::read_to_string(subject_marker_path(&cert_path)).unwrap(),
            current_subject_marker()
        );

        std::fs::remove_dir_all(&dir).unwrap();
    }

    #[test]
    fn reuses_key_and_leaves_cert_alone_when_marker_matches() {
        let dir = temp_dir("stable");
        let cert_path = dir.join("root.crt");
        let key_path = dir.join("root.key");

        load_or_generate(&cert_path, &key_path).unwrap();
        let key_after_first = std::fs::read_to_string(&key_path).unwrap();
        let cert_after_first = std::fs::read_to_string(&cert_path).unwrap();

        load_or_generate(&cert_path, &key_path).unwrap();

        assert_eq!(std::fs::read_to_string(&key_path).unwrap(), key_after_first);
        assert_eq!(std::fs::read_to_string(&cert_path).unwrap(), cert_after_first);

        std::fs::remove_dir_all(&dir).unwrap();
    }

    #[test]
    fn regenerates_stale_cert_when_subject_marker_is_missing_or_mismatched() {
        let dir = temp_dir("stale");
        let cert_path = dir.join("root.crt");
        let key_path = dir.join("root.key");

        load_or_generate(&cert_path, &key_path).unwrap();
        let key_after_first = std::fs::read_to_string(&key_path).unwrap();
        let cert_after_first = std::fs::read_to_string(&cert_path).unwrap();

        // Simulate a pre-rename install: the marker records a different
        // subject than the current COMMON_NAME/ORG_NAME constants.
        std::fs::write(subject_marker_path(&cert_path), "BlockApt DLP Agent Local CA|BlockApt").unwrap();

        load_or_generate(&cert_path, &key_path).unwrap();

        // Key is untouched (leaf-signing trust chain must stay valid for
        // certs already issued under it)...
        assert_eq!(std::fs::read_to_string(&key_path).unwrap(), key_after_first);
        // ...but the stale root.crt is rewritten with the current subject,
        // and the marker now reflects it.
        assert_ne!(std::fs::read_to_string(&cert_path).unwrap(), cert_after_first);
        assert_eq!(
            std::fs::read_to_string(subject_marker_path(&cert_path)).unwrap(),
            current_subject_marker()
        );

        std::fs::remove_dir_all(&dir).unwrap();
    }
}
