//! Shared support code for the `agentd` and `agentctl` binaries.
//!
//! [`runtime`] holds the agent's core startup logic (config/CA/policy
//! loading, PAC serving, running the MITM proxy) so it can be driven
//! identically from a plain foreground process or from the Windows Service
//! Control Manager. [`service`] (Windows-only) is the SCM dispatch/control-
//! handler glue that `agentd --service` runs under. [`service_install`]
//! (Windows-only) is the service registration/recovery-action/uninstall
//! logic `agentctl` drives.

pub mod runtime;

#[cfg(windows)]
pub mod service;

#[cfg(windows)]
pub mod service_install;

/// Windows Service name used to register/open/query the agent's service.
/// Shared between `service` (the SCM entry point) and `service_install` (the
/// installer that registers it) so the two can never drift apart.
pub const SERVICE_NAME: &str = "AiSpmDlpAgent";
/// User-facing name shown in `services.msc`.
pub const SERVICE_DISPLAY_NAME: &str = "AI-SPM DLP Agent";
