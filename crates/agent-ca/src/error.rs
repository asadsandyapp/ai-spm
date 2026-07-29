use std::path::PathBuf;

#[derive(Debug, thiserror::Error)]
pub enum CaError {
    #[error("failed to read {path}: {source}")]
    Read {
        path: PathBuf,
        #[source]
        source: std::io::Error,
    },

    #[error("failed to write {path}: {source}")]
    Write {
        path: PathBuf,
        #[source]
        source: std::io::Error,
    },

    #[error("failed to create directory {path}: {source}")]
    CreateDir {
        path: PathBuf,
        #[source]
        source: std::io::Error,
    },

    #[error("rcgen error: {0}")]
    Rcgen(#[from] rcgen::Error),

    #[error("failed to parse existing policies.json: {0}")]
    Json(#[from] serde_json::Error),

    #[cfg(windows)]
    #[error("windows trust store error: {0}")]
    Windows(#[from] windows::core::Error),

    #[cfg(target_os = "linux")]
    #[error("`{command}` failed: {reason}")]
    Command { command: String, reason: String },
}
