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
