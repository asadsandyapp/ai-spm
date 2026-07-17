//! Marked TCP connections for upstream relay (excluded from transparent redirect).

use std::net::SocketAddr;
use std::time::Duration;

use tokio::net::{lookup_host, TcpStream};
use tracing::debug;

/// Socket mark applied to agent-originated upstream connections so iptables
/// redirect rules do not capture the agent's own outbound TLS.
pub const DEFAULT_SOCKET_MARK: u32 = 0x4149_534d; // "AISPM"

/// Connect to `authority` (`host:port`), preferring IPv4.
pub async fn connect_marked(authority: &str, mark: u32) -> std::io::Result<TcpStream> {
    let mut addrs: Vec<SocketAddr> = lookup_host(authority).await?.collect();
    addrs.sort_by_key(SocketAddr::is_ipv6);

    let mut last_err = None;
    for addr in addrs {
        match connect_upstream_addr(addr, mark).await {
            Ok(stream) => return Ok(stream),
            Err(err) => {
                debug!(%addr, error = %err, "upstream connect failed, trying next address");
                last_err = Some(err);
            }
        }
    }
    Err(last_err.unwrap_or_else(|| {
        std::io::Error::new(
            std::io::ErrorKind::AddrNotAvailable,
            format!("no addresses resolved for {authority}"),
        )
    }))
}

/// Connect to a resolved upstream address for passthrough splicing.
pub async fn connect_upstream_addr(addr: SocketAddr, mark: u32) -> std::io::Result<TcpStream> {
    match connect_with_optional_mark(addr, mark).await {
        Ok(stream) => Ok(stream),
        Err(err) => {
            debug!(%addr, error = %err, "marked connect failed; falling back to direct TCP");
            TcpStream::connect(addr).await
        }
    }
}

async fn connect_with_optional_mark(addr: SocketAddr, mark: u32) -> std::io::Result<TcpStream> {
    #[cfg(unix)]
    {
        use socket2::{Domain, Protocol, Socket, Type};
        use std::os::unix::io::AsRawFd;

        let domain = if addr.is_ipv4() {
            Domain::IPV4
        } else {
            Domain::IPV6
        };
        let socket = Socket::new(domain, Type::STREAM, Some(Protocol::TCP))?;
        set_socket_mark_best_effort(socket.as_raw_fd(), mark);
        socket.set_nonblocking(true)?;
        socket.set_read_timeout(Some(Duration::from_secs(30)))?;
        socket.set_write_timeout(Some(Duration::from_secs(30)))?;
        socket.connect(&addr.into())?;

        let std_stream: std::net::TcpStream = socket.into();
        let stream = TcpStream::from_std(std_stream)?;
        stream.writable().await?;
        if let Some(err) = stream.take_error()? {
            return Err(err);
        }
        Ok(stream)
    }

    #[cfg(not(unix))]
    {
        let _ = mark;
        TcpStream::connect(addr).await
    }
}

#[cfg(unix)]
fn set_socket_mark_best_effort(fd: std::os::unix::io::RawFd, mark: u32) {
    let ret = unsafe {
        libc::setsockopt(
            fd,
            libc::SOL_SOCKET,
            libc::SO_MARK,
            &mark as *const u32 as *const libc::c_void,
            std::mem::size_of::<u32>() as libc::socklen_t,
        )
    };
    if ret != 0 {
        let err = std::io::Error::last_os_error();
        debug!(error = %err, "SO_MARK unavailable; relying on iptables uid-owner exclusion");
    }
}
