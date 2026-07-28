//! Registers, configures, and removes the `agentd` Windows Service. Used by
//! `agentctl install --full` / `agentctl uninstall`; kept separate from
//! `agentctl.rs` so the SCM-facing logic is isolated from CLI/argument
//! handling.

use std::ffi::OsString;
use std::path::Path;
use std::time::Duration;

use windows_service::service::{
    ServiceAccess, ServiceAction, ServiceActionType, ServiceErrorControl, ServiceFailureActions,
    ServiceFailureResetPeriod, ServiceInfo, ServiceStartType, ServiceState, ServiceType,
};
use windows_service::service_manager::{ServiceManager, ServiceManagerAccess};

const SERVICE_TYPE: ServiceType = ServiceType::OWN_PROCESS;

/// Register `agentd` as an auto-start Windows Service running as
/// LocalSystem, whose start command is `<agentd_exe> --service --config
/// <config_path>`, give it SCM-native crash-restart recovery actions, and
/// start it immediately. Requires an elevated process (creating a service
/// needs `SC_MANAGER_CREATE_SERVICE`).
pub fn install(agentd_exe: &Path, config_path: &Path) -> anyhow::Result<()> {
    let manager = ServiceManager::local_computer(
        None::<&str>,
        ServiceManagerAccess::CONNECT | ServiceManagerAccess::CREATE_SERVICE,
    )?;

    let info = ServiceInfo {
        name: OsString::from(crate::SERVICE_NAME),
        display_name: OsString::from(crate::SERVICE_DISPLAY_NAME),
        service_type: SERVICE_TYPE,
        start_type: ServiceStartType::AutoStart,
        error_control: ServiceErrorControl::Normal,
        executable_path: agentd_exe.to_path_buf(),
        launch_arguments: vec![
            OsString::from("--service"),
            OsString::from("--config"),
            OsString::from(config_path.as_os_str()),
        ],
        dependencies: vec![],
        account_name: None, // LocalSystem
        account_password: None,
    };

    let service = manager.create_service(&info, ServiceAccess::ALL_ACCESS)?;

    // SCM-native recovery: restart at 30s/60s/120s on the first three
    // failures in a day, then keep repeating the last action; the failure
    // counter resets after a day with no failures. This is what makes
    // `agentd` recover from a crash on its own - no external supervisor
    // process, and it applies from boot before any interactive logon.
    service.update_failure_actions(ServiceFailureActions {
        reset_period: ServiceFailureResetPeriod::After(Duration::from_secs(24 * 60 * 60)),
        reboot_msg: None,
        command: None,
        actions: Some(vec![
            ServiceAction {
                action_type: ServiceActionType::Restart,
                delay: Duration::from_secs(30),
            },
            ServiceAction {
                action_type: ServiceActionType::Restart,
                delay: Duration::from_secs(60),
            },
            ServiceAction {
                action_type: ServiceActionType::Restart,
                delay: Duration::from_secs(120),
            },
        ]),
    })?;
    // By default the recovery actions above only apply when the process
    // crashes or is killed. A DLP agent that exits cleanly on its own (e.g.
    // an unhandled panic that still unwinds to a clean exit) going quiet is
    // just as much a coverage gap, so cover non-crash exits too.
    service.set_failure_actions_on_non_crash_failures(true)?;

    service.start::<&str>(&[])?;

    Ok(())
}

/// Stop (if running) and delete the `agentd` Windows Service. Requires an
/// elevated process.
pub fn uninstall() -> anyhow::Result<()> {
    let manager = ServiceManager::local_computer(None::<&str>, ServiceManagerAccess::CONNECT)?;
    let service = manager.open_service(crate::SERVICE_NAME, ServiceAccess::ALL_ACCESS)?;

    if service.query_status()?.current_state != ServiceState::Stopped {
        service.stop()?;
        // `stop()` requests a stop; SCM still needs a moment to actually
        // tear the process down before `delete()` can finish (delete just
        // marks the service for removal once nothing references it).
        for _ in 0..40 {
            if service.query_status()?.current_state == ServiceState::Stopped {
                break;
            }
            std::thread::sleep(Duration::from_millis(250));
        }
    }

    service.delete()?;
    Ok(())
}
