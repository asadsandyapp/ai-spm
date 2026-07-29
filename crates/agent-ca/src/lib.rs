pub mod ca;
pub mod error;
pub mod firefox;

#[cfg(windows)]
pub mod winstore;

#[cfg(target_os = "linux")]
pub mod linux_trust;

pub use ca::{load_or_generate, GeneratedCa, COMMON_NAME};
pub use error::CaError;

#[cfg(windows)]
pub use winstore::{install_root_cert, remove_root_cert, StoreScope};

#[cfg(target_os = "linux")]
pub use linux_trust::{install_root_cert, remove_root_cert, StoreScope};
