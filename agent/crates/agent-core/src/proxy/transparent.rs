//! Transparent network interception — browser-agnostic TLS capture at the OS layer.
//!
//! On Linux, outbound TCP/443 is redirected here via iptables/nftables. Each
//! connection's original destination is recovered with `SO_ORIGINAL_DST`, the TLS
//! ClientHello SNI is peeked, and only AI provider traffic is MITM-inspected;
//! everything else is spliced through untouched.

use std::net::SocketAddr;
use std::sync::Arc;

use tokio::io::copy_bidirectional;
use tokio::net::{TcpListener, TcpStream};
use tokio::sync::watch;
use tracing::{debug, info};

use super::mitm;
use super::sni::parse_sni_from_client_hello;
use super::tcp::connect_upstream_addr;
use super::{ProxyError, ProxyState};

/// Run the transparent TLS interceptor until shutdown.
pub async fn run_transparent_proxy(
    listen: SocketAddr,
    state: Arc<ProxyState>,
    socket_mark: u32,
    mut shutdown: watch::Receiver<bool>,
) -> Result<(), ProxyError> {
    let listener = TcpListener::bind(listen).await.map_err(ProxyError::Bind)?;

    info!(
        %listen,
        socket_mark,
        "transparent network interceptor listening — all outbound HTTPS is classified here"
    );

    loop {
        tokio::select! {
            _ = shutdown.changed() => {
                if *shutdown.borrow() {
                    info!("transparent interceptor shutting down");
                    return Ok(());
                }
            }
            accept = listener.accept() => {
                let (stream, peer) = accept.map_err(ProxyError::Accept)?;
                let state = Arc::clone(&state);
                tokio::spawn(async move {
                    if let Err(err) = handle_transparent_connection(stream, peer, state, socket_mark).await {
                        debug!(%peer, error = %err, "transparent connection ended");
                    }
                });
            }
        }
    }
}

async fn handle_transparent_connection(
    stream: TcpStream,
    peer: SocketAddr,
    state: Arc<ProxyState>,
    socket_mark: u32,
) -> Result<(), String> {
    let orig_dest = original_destination(&stream).map_err(|e| e.to_string())?;

    let mut peek_buf = [0u8; 4096];
    let peek_len = stream
        .peek(&mut peek_buf)
        .await
        .map_err(|e| e.to_string())?;

    let sni = parse_sni_from_client_hello(&peek_buf[..peek_len]);
    let host = sni.unwrap_or_else(|| orig_dest.ip().to_string());

    if state.should_mitm(&host) {
        info!(
            %peer,
            %host,
            %orig_dest,
            "transparent intercept — AI provider MITM"
        );
        mitm::spawn_transparent_mitm(stream, host, orig_dest.port(), state);
        Ok(())
    } else {
        debug!(%peer, %host, %orig_dest, "transparent splice — passthrough");
        splice_passthrough(stream, orig_dest, socket_mark)
            .await
            .map_err(|e| e.to_string())
    }
}

async fn splice_passthrough(
    mut client: TcpStream,
    upstream: SocketAddr,
    socket_mark: u32,
) -> std::io::Result<()> {
    let mut server = connect_upstream_addr(upstream, socket_mark).await?;
    copy_bidirectional(&mut client, &mut server).await?;
    Ok(())
}

#[cfg(target_os = "linux")]
fn original_destination(stream: &TcpStream) -> std::io::Result<SocketAddr> {
    use std::mem::{size_of, MaybeUninit};
    use std::net::{Ipv4Addr, Ipv6Addr};
    use std::os::unix::io::AsRawFd;

    const SO_ORIGINAL_DST: libc::c_int = 80;
    let fd = stream.as_raw_fd();

    unsafe {
        let mut addr: MaybeUninit<libc::sockaddr_in> = MaybeUninit::uninit();
        let mut len = size_of::<libc::sockaddr_in>() as libc::socklen_t;
        let ret = libc::getsockopt(
            fd,
            libc::SOL_IP,
            SO_ORIGINAL_DST,
            addr.as_mut_ptr().cast(),
            &mut len,
        );
        if ret == 0 && len as usize >= size_of::<libc::sockaddr_in>() {
            let addr = addr.assume_init();
            if addr.sin_family as i32 == libc::AF_INET {
                let ip = Ipv4Addr::from(u32::from_be(addr.sin_addr.s_addr));
                let port = u16::from_be(addr.sin_port);
                return Ok(SocketAddr::from((ip, port)));
            }
        }

        let mut addr6: MaybeUninit<libc::sockaddr_in6> = MaybeUninit::uninit();
        let mut len6 = size_of::<libc::sockaddr_in6>() as libc::socklen_t;
        let ret6 = libc::getsockopt(
            fd,
            libc::SOL_IPV6,
            SO_ORIGINAL_DST,
            addr6.as_mut_ptr().cast(),
            &mut len6,
        );
        if ret6 == 0 && len6 as usize >= size_of::<libc::sockaddr_in6>() {
            let addr6 = addr6.assume_init();
            if addr6.sin6_family as i32 == libc::AF_INET6 {
                let ip = Ipv6Addr::from(addr6.sin6_addr.s6_addr);
                let port = u16::from_be(addr6.sin6_port);
                return Ok(SocketAddr::from((ip, port)));
            }
        }
    }

    Err(std::io::Error::new(
        std::io::ErrorKind::Other,
        "SO_ORIGINAL_DST unavailable (not a redirected connection?)",
    ))
}

#[cfg(not(target_os = "linux"))]
fn original_destination(_stream: &TcpStream) -> std::io::Result<SocketAddr> {
    Err(std::io::Error::new(
        std::io::ErrorKind::Unsupported,
        "transparent interception is only supported on Linux",
    ))
}

#[cfg(test)]
mod tests {
    #[test]
    fn default_socket_mark_is_stable() {
        assert_eq!(crate::proxy::DEFAULT_SOCKET_MARK, 0x4149_534d);
    }
}
