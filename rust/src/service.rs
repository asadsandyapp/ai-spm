//! Windows Service Control Manager integration for `agentd`. Only meaningful
//! when SCM itself launched the process - the service's registered start
//! command (set up by [`crate::service_install::install`]) invokes
//! `agentd.exe --service --config <path>`; running this entry point outside
//! of SCM fails immediately with `ERROR_FAILED_SERVICE_CONTROLLER_CONNECT`,
//! which is why `agentd`'s plain console mode is a separate code path (see
//! `src/bin/agentd.rs`) rather than something this module falls back to.

use std::ffi::OsString;
use std::path::PathBuf;
use std::sync::mpsc;
use std::sync::OnceLock;
use std::time::Duration;

use windows_service::service::{
    ServiceControl, ServiceControlAccept, ServiceExitCode, ServiceState, ServiceStatus, ServiceType,
};
use windows_service::service_control_handler::{
    self, ServiceControlHandlerResult, ServiceStatusHandle,
};
use windows_service::{define_windows_service, service_dispatcher};

const SERVICE_TYPE: ServiceType = ServiceType::OWN_PROCESS;

// `service_main` (below) is invoked by SCM through a raw `extern "system"`
// entry point with no way to pass our own typed arguments through it - the
// config path has to reach it via a process-wide static, set just before
// entering the dispatcher.
static CONFIG_PATH: OnceLock<PathBuf> = OnceLock::new();

define_windows_service!(ffi_service_main, service_main);

/// Enter the SCM's service dispatch loop; blocks the calling thread until
/// the service is asked to stop. Returns an error immediately (no threads
/// spawned) if this process wasn't actually launched by SCM.
pub fn run(config_path: PathBuf) -> windows_service::Result<()> {
    CONFIG_PATH
        .set(config_path)
        .expect("service::run must only be called once per process");
    service_dispatcher::start(crate::SERVICE_NAME, ffi_service_main)
}

fn service_main(_arguments: Vec<OsString>) {
    if let Err(err) = run_service() {
        // No console is attached under SCM, and the file logger isn't set up
        // yet at this point (it's configured inside `run_agent`, once the
        // config has loaded) - this is best-effort visibility only. A
        // Windows Event Log sink is a tracked follow-up, not solved here
        // (see README's "Not yet implemented").
        eprintln!("AI-SPM DLP Agent service failed: {err:#}");
    }
}

fn run_service() -> anyhow::Result<()> {
    let (shutdown_tx, shutdown_rx) = mpsc::channel::<()>();

    let event_handler = move |control_event| -> ServiceControlHandlerResult {
        match control_event {
            ServiceControl::Interrogate => ServiceControlHandlerResult::NoError,
            ServiceControl::Stop | ServiceControl::Shutdown => {
                let _ = shutdown_tx.send(());
                ServiceControlHandlerResult::NoError
            }
            _ => ServiceControlHandlerResult::NotImplemented,
        }
    };

    let status_handle = service_control_handler::register(crate::SERVICE_NAME, event_handler)?;
    report(&status_handle, ServiceState::StartPending, ServiceControlAccept::empty(), 10);

    let config_path = CONFIG_PATH
        .get()
        .expect("config path set before service_dispatcher::start")
        .clone();

    let runtime = tokio::runtime::Runtime::new()?;

    // The stop/shutdown control handler above runs on SCM's own thread and
    // can only communicate via the std mpsc channel; bridge it into the
    // async world with a dedicated blocking task rather than polling.
    let shutdown = async move {
        let _ = tokio::task::spawn_blocking(move || shutdown_rx.recv()).await;
    };

    report(
        &status_handle,
        ServiceState::Running,
        ServiceControlAccept::STOP | ServiceControlAccept::SHUTDOWN,
        0,
    );

    let result = runtime.block_on(crate::runtime::run_agent(config_path, shutdown));

    report(&status_handle, ServiceState::StopPending, ServiceControlAccept::empty(), 5);
    if let Err(err) = &result {
        eprintln!("AI-SPM DLP Agent service exited with error: {err:#}");
    }
    report(&status_handle, ServiceState::Stopped, ServiceControlAccept::empty(), 0);

    result
}

fn report(
    handle: &ServiceStatusHandle,
    state: ServiceState,
    controls_accepted: ServiceControlAccept,
    wait_hint_secs: u64,
) {
    // Best-effort: if SCM has already stopped listening there's nothing
    // useful to do with a failure to report status.
    let _ = handle.set_service_status(ServiceStatus {
        service_type: SERVICE_TYPE,
        current_state: state,
        controls_accepted,
        exit_code: ServiceExitCode::Win32(0),
        checkpoint: 0,
        wait_hint: Duration::from_secs(wait_hint_secs),
        process_id: None,
    });
}
