//! Installs the local root CA into the current Windows user's Trusted Root
//! store (`CERT_SYSTEM_STORE_CURRENT_USER`), which requires no elevation.
//! A machine-wide install (for real deployment) is a follow-up milestone.

use std::ffi::c_void;

use windows::core::{PCSTR, PCWSTR};
use windows::Win32::Security::Cryptography::{
    CertAddEncodedCertificateToStore, CertCloseStore, CertDeleteCertificateFromStore,
    CertDuplicateCertificateContext, CertEnumCertificatesInStore, CertFreeCertificateContext,
    CertGetNameStringW, CertOpenStore, CERT_NAME_SIMPLE_DISPLAY_TYPE, CERT_OPEN_STORE_FLAGS,
    CERT_QUERY_ENCODING_TYPE, CERT_STORE_ADD_REPLACE_EXISTING, CERT_STORE_PROV_SYSTEM,
    CERT_SYSTEM_STORE_CURRENT_USER, CERT_SYSTEM_STORE_LOCAL_MACHINE, PKCS_7_ASN_ENCODING,
    X509_ASN_ENCODING,
};

use crate::error::CaError;

const ROOT_STORE_NAME: &str = "Root";

/// Which Windows certificate store scope to install the CA into.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum StoreScope {
    /// `CERT_SYSTEM_STORE_CURRENT_USER` - covers only the invoking user, no
    /// elevation required. Used by the granular `agentctl install-ca`
    /// subcommand (dev/test/troubleshooting - matches this project's
    /// original no-admin-required install model).
    CurrentUser,
    /// `CERT_SYSTEM_STORE_LOCAL_MACHINE` - covers every account on the
    /// machine (so browsers and the ChatGPT desktop app trust the CA
    /// regardless of which user is signed in), but requires an elevated
    /// process to write. Used by `agentctl install --full`, the path a real
    /// installer drives (see ROADMAP.md's install/packaging milestone).
    LocalMachine,
}

impl StoreScope {
    fn flags(self) -> CERT_OPEN_STORE_FLAGS {
        match self {
            StoreScope::CurrentUser => CERT_OPEN_STORE_FLAGS(CERT_SYSTEM_STORE_CURRENT_USER),
            StoreScope::LocalMachine => CERT_OPEN_STORE_FLAGS(CERT_SYSTEM_STORE_LOCAL_MACHINE),
        }
    }
}

/// Install `cert_der` (a DER-encoded X.509 certificate) into the Windows
/// Trusted Root Certification Authorities store at the given `scope`.
pub fn install_root_cert(cert_der: &[u8], scope: StoreScope) -> Result<(), CaError> {
    let store_name_wide: Vec<u16> = ROOT_STORE_NAME
        .encode_utf16()
        .chain(std::iter::once(0))
        .collect();
    let encoding = CERT_QUERY_ENCODING_TYPE(X509_ASN_ENCODING.0 | PKCS_7_ASN_ENCODING.0);

    unsafe {
        let store = CertOpenStore(
            PCSTR(CERT_STORE_PROV_SYSTEM as usize as *const u8),
            CERT_QUERY_ENCODING_TYPE(0),
            None,
            scope.flags(),
            Some(PCWSTR::from_raw(store_name_wide.as_ptr()).0 as *const c_void),
        )?;

        let add_result = CertAddEncodedCertificateToStore(
            Some(store),
            encoding,
            cert_der,
            CERT_STORE_ADD_REPLACE_EXISTING,
            None,
        );
        let close_result = CertCloseStore(Some(store), 0);

        add_result?;
        close_result?;
    }

    Ok(())
}

/// Best-effort removal of every certificate in `scope`'s Trusted Root store
/// whose subject's simple display name equals `common_name`. Returns how
/// many were deleted. Used by `agentctl uninstall` - Windows may keep a
/// certificate cached/in-use elsewhere (e.g. a still-running browser) and
/// refuse deletion, which is expected, not an error: callers should log the
/// count and move on rather than treating a low/zero count as failure.
pub fn remove_root_cert(common_name: &str, scope: StoreScope) -> Result<usize, CaError> {
    let store_name_wide: Vec<u16> = ROOT_STORE_NAME
        .encode_utf16()
        .chain(std::iter::once(0))
        .collect();

    unsafe {
        let store = CertOpenStore(
            PCSTR(CERT_STORE_PROV_SYSTEM as usize as *const u8),
            CERT_QUERY_ENCODING_TYPE(0),
            None,
            scope.flags(),
            Some(PCWSTR::from_raw(store_name_wide.as_ptr()).0 as *const c_void),
        )?;

        let mut removed = 0usize;

        // `CertEnumCertificatesInStore` frees the context passed as
        // `pPrevCertContext` once it's used to find the next entry, and
        // deleting an entry invalidates the store's iteration state - the
        // only entries expected here are at most one or two (this CA's
        // current and perhaps a stale prior-rename cert), so the simplest
        // correct approach is to keep enumerating past whatever doesn't
        // match, and only touch iteration state via the normal "next"
        // call - never continuing to enumerate through a context we just
        // deleted.
        let mut ctx = CertEnumCertificatesInStore(store, None);
        while !ctx.is_null() {
            let mut name_buf = [0u16; 256];
            let len = CertGetNameStringW(ctx, CERT_NAME_SIMPLE_DISPLAY_TYPE, 0, None, Some(&mut name_buf));
            let name = String::from_utf16_lossy(&name_buf[..(len as usize).saturating_sub(1)]);

            if name == common_name {
                // `CertDeleteCertificateFromStore` frees the context it's
                // given on success (and requires the caller to free it
                // manually on failure) - duplicate first so the original
                // `ctx` stays valid for advancing enumeration regardless of
                // which way deletion goes.
                let owned = CertDuplicateCertificateContext(Some(ctx));
                match CertDeleteCertificateFromStore(owned) {
                    Ok(()) => removed += 1,
                    Err(_) => {
                        let _ = CertFreeCertificateContext(Some(owned));
                    }
                }
            }

            ctx = CertEnumCertificatesInStore(store, Some(ctx));
        }

        CertCloseStore(Some(store), 0)?;
        Ok(removed)
    }
}
