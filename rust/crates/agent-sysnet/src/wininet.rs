//! Configures the current Windows user's proxy settings to use a PAC
//! (Proxy Auto-Config) script, so only the domains listed in the PAC are
//! routed through the local proxy - everything else bypasses it entirely.
//! Per-user (`HKEY_CURRENT_USER`), no elevation required.

use winreg::enums::{HKEY_CURRENT_USER, KEY_SET_VALUE};
use winreg::RegKey;

use crate::error::SysnetError;

const INTERNET_SETTINGS_KEY: &str = r"Software\Microsoft\Windows\CurrentVersion\Internet Settings";

// wininet.h constants (stable across Windows versions).
const INTERNET_OPTION_REFRESH: u32 = 37;
const INTERNET_OPTION_SETTINGS_CHANGED: u32 = 39;

/// Point the current user's proxy configuration at the PAC served at
/// `pac_url`, and disable any manual proxy server setting so the PAC is the
/// sole authority on what gets proxied. `pac_url` must be an `http://` URL
/// (served by `agentd`) — Chromium browsers silently ignore `file://` PAC
/// URLs, so a file path here would leave Chrome/Edge unproxied.
pub fn set_pac_url(pac_url: &str) -> Result<(), SysnetError> {
    let hkcu = RegKey::predef(HKEY_CURRENT_USER);
    let settings = hkcu.open_subkey_with_flags(INTERNET_SETTINGS_KEY, KEY_SET_VALUE)?;
    settings.set_value("AutoConfigURL", &pac_url.to_string())?;
    settings.set_value("ProxyEnable", &0u32)?;

    refresh();
    Ok(())
}

/// Remove the PAC configuration, reverting to no proxy.
pub fn clear_pac_url() -> Result<(), SysnetError> {
    let hkcu = RegKey::predef(HKEY_CURRENT_USER);
    let settings = hkcu.open_subkey_with_flags(INTERNET_SETTINGS_KEY, KEY_SET_VALUE)?;
    let _ = settings.delete_value("AutoConfigURL");
    settings.set_value("ProxyEnable", &0u32)?;

    refresh();
    Ok(())
}

fn refresh() {
    unsafe {
        use windows::Win32::Networking::WinInet::InternetSetOptionW;
        let _ = InternetSetOptionW(None, INTERNET_OPTION_SETTINGS_CHANGED, None, 0);
        let _ = InternetSetOptionW(None, INTERNET_OPTION_REFRESH, None, 0);
    }
}
