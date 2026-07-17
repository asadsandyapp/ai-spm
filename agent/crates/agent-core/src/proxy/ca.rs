//! Local MITM certificate authority — generates a root CA on first run and
//! issues per-hostname leaf certificates signed by that CA.

use std::fs;
use std::path::{Path, PathBuf};
use std::sync::Arc;

use dashmap::DashMap;
use rcgen::{
    BasicConstraints, CertificateParams, DistinguishedName, DnType, ExtendedKeyUsagePurpose, IsCa,
    Issuer, KeyPair, KeyUsagePurpose,
};
use rustls::pki_types::{CertificateDer, PrivateKeyDer, PrivatePkcs8KeyDer};
use rustls::ServerConfig;
use thiserror::Error;
use tracing::info;

const CA_CERT_FILE: &str = "mitm-ca.crt";
const CA_KEY_FILE: &str = "mitm-ca.key";

#[derive(Debug, Error)]
pub enum CaError {
    #[error("IO error: {0}")]
    Io(#[from] std::io::Error),
    #[error("certificate generation failed: {0}")]
    Rcgen(#[from] rcgen::Error),
    #[error("TLS configuration failed: {0}")]
    Tls(String),
}

/// Holds the MITM root CA and a cache of per-hostname server configs.
pub struct MitmCertificateAuthority {
    ca_dir: PathBuf,
    ca_cert_pem: String,
    issuer: Issuer<'static, KeyPair>,
    server_cache: DashMap<String, Arc<ServerConfig>>,
}

impl MitmCertificateAuthority {
    /// Load an existing CA from `ca_dir`, or generate a new one on first run.
    pub fn load_or_create(ca_dir: &Path) -> Result<Self, CaError> {
        fs::create_dir_all(ca_dir)?;

        let cert_path = ca_dir.join(CA_CERT_FILE);
        let key_path = ca_dir.join(CA_KEY_FILE);

        let (issuer, ca_cert_pem) = if cert_path.exists() && key_path.exists() {
            info!(path = %ca_dir.display(), "loading existing MITM CA");
            let cert_pem = fs::read_to_string(&cert_path)?;
            let key_pem = fs::read_to_string(&key_path)?;
            let key_pair = KeyPair::from_pem(&key_pem)?;
            let issuer = Issuer::from_ca_cert_pem(&cert_pem, key_pair)?;
            (issuer, cert_pem)
        } else {
            info!(path = %ca_dir.display(), "generating new MITM root CA");
            let mut dn = DistinguishedName::new();
            dn.push(DnType::CommonName, "AI-SPM MITM CA");
            dn.push(DnType::OrganizationName, "AI-SPM Platform");

            let mut params = CertificateParams::default();
            params.distinguished_name = dn;
            params.is_ca = IsCa::Ca(BasicConstraints::Unconstrained);
            params.key_usages = vec![KeyUsagePurpose::KeyCertSign, KeyUsagePurpose::CrlSign];

            let key_pair = KeyPair::generate()?;
            let cert = params.self_signed(&key_pair)?;
            let cert_pem = cert.pem();
            let key_pem = key_pair.serialize_pem();

            fs::write(&cert_path, &cert_pem)?;
            fs::write(&key_path, &key_pem)?;
            #[cfg(unix)]
            fs::set_permissions(&key_path, fs::Permissions::from_mode(0o600)).ok();

            info!(
                ca_cert = %cert_path.display(),
                "MITM CA created — install this certificate in your OS/browser trust store"
            );

            let issuer = Issuer::new(params, key_pair);
            (issuer, cert_pem)
        };

        Ok(Self {
            ca_dir: ca_dir.to_path_buf(),
            ca_cert_pem,
            issuer,
            server_cache: DashMap::new(),
        })
    }

    pub fn ca_cert_path(&self) -> PathBuf {
        self.ca_dir.join(CA_CERT_FILE)
    }

    pub fn ca_cert_pem(&self) -> &str {
        &self.ca_cert_pem
    }

    /// Return a rustls `ServerConfig` with a leaf certificate valid for `hostname`.
    pub fn server_config_for_host(&self, hostname: &str) -> Result<Arc<ServerConfig>, CaError> {
        if let Some(cached) = self.server_cache.get(hostname) {
            return Ok(Arc::clone(&cached));
        }

        let mut dn = DistinguishedName::new();
        dn.push(DnType::CommonName, hostname);

        let mut params = CertificateParams::new(vec![hostname.to_string()])?;
        params.distinguished_name = dn;
        params.is_ca = IsCa::NoCa;
        params.key_usages = vec![
            KeyUsagePurpose::DigitalSignature,
            KeyUsagePurpose::KeyEncipherment,
        ];
        params.extended_key_usages = vec![ExtendedKeyUsagePurpose::ServerAuth];

        let leaf_key = KeyPair::generate()?;
        let leaf_cert = params.signed_by(&leaf_key, &self.issuer)?;

        let cert_chain = vec![CertificateDer::from(leaf_cert.der().to_vec())];
        let key_der = PrivateKeyDer::Pkcs8(PrivatePkcs8KeyDer::from(leaf_key.serialize_der()));

        let mut config = ServerConfig::builder()
            .with_no_client_auth()
            .with_single_cert(cert_chain, key_der)
            .map_err(|e| CaError::Tls(e.to_string()))?;

        // Advertise HTTP/2 + HTTP/1.1 so browsers (Chrome) negotiate h2 to AI web UIs.
        config.alpn_protocols = vec![b"h2".to_vec(), b"http/1.1".to_vec()];

        let arc = Arc::new(config);
        self.server_cache
            .insert(hostname.to_string(), Arc::clone(&arc));
        Ok(arc)
    }
}

#[cfg(unix)]
use std::os::unix::fs::PermissionsExt;
