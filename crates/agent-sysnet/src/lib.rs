pub mod error;
pub mod pac;

#[cfg(windows)]
pub mod wininet;

pub use error::SysnetError;
pub use pac::render_pac;

#[cfg(windows)]
pub use wininet::{clear_pac_url, set_pac_url};
