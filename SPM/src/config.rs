/// Runtime configuration loaded from environment variables.
#[derive(Debug, Clone)]
pub struct Config {
    /// Full URL of the upstream AI endpoint (e.g. `http://localhost:8080/chat`).
    pub upstream_url: String,
    /// Address the proxy listens on (default: `0.0.0.0:3000`).
    pub listen_addr: String,
}

impl Config {
    /// Load configuration from the environment.
    ///
    /// `UPSTREAM_URL` is required. `LISTEN_ADDR` is optional.
    pub fn from_env() -> Result<Self, String> {
        let upstream_url = std::env::var("UPSTREAM_URL").map_err(|_| {
            "UPSTREAM_URL environment variable is required (e.g. http://localhost:8080/chat)"
                .to_string()
        })?;

        let listen_addr =
            std::env::var("LISTEN_ADDR").unwrap_or_else(|_| "0.0.0.0:3000".to_string());

        Ok(Self {
            upstream_url,
            listen_addr,
        })
    }
}
