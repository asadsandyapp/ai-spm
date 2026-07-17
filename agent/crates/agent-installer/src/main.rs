//! AI-SPM Linux agent installer launcher.
//!
//! Default employee UX: auto-elevate `install-agent.sh` (password dialog only).
//! No python3-tk required. Set `AISPM_FORCE_GUI=1` for the optional Tk wizard.

use std::env;
use std::path::PathBuf;
use std::process::{Command, Stdio};

fn package_dir() -> PathBuf {
    env::current_exe()
        .ok()
        .and_then(|p| p.parent().map(|d| d.to_path_buf()))
        .unwrap_or_else(|| env::current_dir().unwrap_or_else(|_| PathBuf::from(".")))
}

fn tkinter_available() -> bool {
    Command::new("python3")
        .args(["-c", "import tkinter"])
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .status()
        .map(|s| s.success())
        .unwrap_or(false)
}

fn run_auto_install(here: &PathBuf) -> ! {
    let shell = here.join("aispm-agent-installer.sh");
    let fallback = here.join("run-install-cli.sh");
    let script = if shell.is_file() {
        shell
    } else if fallback.is_file() {
        fallback
    } else {
        eprintln!("ERROR: aispm-agent-installer.sh missing from package.");
        std::process::exit(1);
    };

    let status = Command::new("bash")
        .arg(&script)
        .current_dir(here)
        .stdin(Stdio::inherit())
        .stdout(Stdio::inherit())
        .stderr(Stdio::inherit())
        .status();
    match status {
        Ok(s) => std::process::exit(s.code().unwrap_or(1)),
        Err(err) => {
            eprintln!("Failed to start installer: {err}");
            std::process::exit(1);
        }
    }
}

fn main() {
    let here = package_dir();
    let enrollment = here.join("enrollment.env");
    if !enrollment.is_file() {
        eprintln!(
            "ERROR: enrollment.env missing next to the installer.\n\
             Download the organization package from Admin → Download Agent."
        );
        std::process::exit(1);
    }

    let force_gui = env::var("AISPM_FORCE_GUI").ok().as_deref() == Some("1");
    let gui = here.join("aispm-agent-installer-gui.py");
    let has_display = env::var_os("DISPLAY").is_some() || env::var_os("WAYLAND_DISPLAY").is_some();
    if force_gui && gui.is_file() && has_display && tkinter_available() {
        let status = Command::new("python3")
            .arg(&gui)
            .current_dir(&here)
            .stdin(Stdio::inherit())
            .stdout(Stdio::inherit())
            .stderr(Stdio::inherit())
            .status();
        match status {
            Ok(s) if s.success() => std::process::exit(0),
            Ok(s) => {
                eprintln!(
                    "GUI installer exited with {} — falling back to auto-install.",
                    s.code().unwrap_or(1)
                );
            }
            Err(err) => {
                eprintln!("GUI launch failed ({err}); falling back to auto-install.");
            }
        }
    }

    run_auto_install(&here);
}
