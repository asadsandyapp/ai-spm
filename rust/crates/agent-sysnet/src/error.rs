use std::path::PathBuf;

#[derive(Debug, thiserror::Error)]
pub enum SysnetError {
    #[error("failed to write PAC file to {path}: {source}")]
    WritePac {
        path: PathBuf,
        #[source]
        source: std::io::Error,
    },

    #[cfg(windows)]
    #[error("registry error: {0}")]
    Registry(#[from] std::io::Error),
}
