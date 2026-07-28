pub mod ca;
pub mod error;

#[cfg(windows)]
pub mod firefox;

#[cfg(windows)]
pub mod winstore;

pub use ca::{load_or_generate, GeneratedCa, COMMON_NAME};
pub use error::CaError;

#[cfg(windows)]
pub use winstore::{install_root_cert, remove_root_cert, StoreScope};
