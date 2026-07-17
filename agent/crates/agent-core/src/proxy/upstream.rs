//! Chrome-impersonating upstream TLS client for Cloudflare-protected AI hosts.
//!
//! Enterprise MITM proxies must re-origin TLS connections to upstream servers
//! (ChatGPT, Claude, etc.) using a fingerprint that matches a real browser.
//! Cloudflare Turnstile pins its clearance to the TLS + HTTP/2 fingerprint of
//! the connection that passed the challenge. Standard rustls/hyper produce a
//! non-browser fingerprint → infinite "Verifying…" loop.
//!
//! BoringSSL is Chrome's actual TLS stack. Configuring it with Chrome's cipher
//! suite order, curves, ALPN, and extension layout produces a ClientHello that
//! Cloudflare accepts as a genuine Chrome browser.

use bytes::Bytes;
use http_body_util::Full;
use hyper_boring::HttpsConnector;
use hyper_util::client::legacy::connect::HttpConnector;
use hyper_util::client::legacy::Client;
use hyper_util::rt::TokioExecutor;
use tracing::info;

use boring::ssl::{SslConnector, SslMethod, SslVerifyMode};

pub type BoxError = Box<dyn std::error::Error + Send + Sync + 'static>;
pub type HttpClient = Client<HttpsConnector<HttpConnector>, Full<Bytes>>;

/// Build an upstream HTTP client that impersonates Chrome TLS/HTTP/2 fingerprints.
pub fn build_chrome_upstream_client() -> Result<HttpClient, BoxError> {
    let mut ssl = SslConnector::builder(SslMethod::tls())?;

    // Chrome ALPN: h2 first, then http/1.1
    ssl.set_alpn_protos(b"\x02h2\x08http/1.1")?;

    // Chrome cipher suite order
    ssl.set_cipher_list(
        "TLS_AES_128_GCM_SHA256:TLS_AES_256_GCM_SHA384:TLS_CHACHA20_POLY1305_SHA256:\
         ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:\
         ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384:\
         ECDHE-ECDSA-CHACHA20-POLY1305:ECDHE-RSA-CHACHA20-POLY1305:\
         ECDHE-RSA-AES128-SHA:ECDHE-RSA-AES256-SHA:\
         AES128-GCM-SHA256:AES256-GCM-SHA384:AES128-SHA256:AES256-SHA384:AES128-SHA:AES256-SHA",
    )?;

    // Chrome supported groups (curves)
    ssl.set_curves_list("X25519:P-256:P-384")?;

    ssl.set_verify(SslVerifyMode::PEER);

    let mut http = HttpConnector::new();
    http.enforce_http(false);

    let mut https = HttpsConnector::with_connector(http, ssl)?;

    https.set_ssl_callback(|ssl, uri| {
        if let Some(host) = uri.host() {
            ssl.set_hostname(host)?;
        }
        Ok(())
    });

    info!("upstream client configured with Chrome TLS fingerprint (BoringSSL)");

    Ok(Client::builder(TokioExecutor::new()).build(https))
}
