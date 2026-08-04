//! AI-SPM agent system tray.
//!
//! Polls agent-service's `local_api` `GET /status` (see
//! `agent-core/src/status.rs` + `agent-core/src/local_api.rs`) over plain
//! loopback HTTP rather than linking `agent-core` directly, so this crate
//! stays free of the BoringSSL/MITM dependency chain that the service needs.
//! Reflects Protected / Disconnected / Blocked in the tray tooltip + menu and
//! fires a desktop notification the first time a new block event appears.
//!
//! `local_api` (and therefore `/status`) is only started when
//! `AISPM_LOCAL_API_ENABLED=1` or transparent mode is on — see
//! `agent-service/src/main.rs`. If it's unreachable, the tray shows
//! Disconnected rather than silently going blank.

use std::sync::{Arc, Mutex};
use std::time::{Duration, SystemTime, UNIX_EPOCH};

use serde::Deserialize;
use tauri::menu::{Menu, MenuItem, PredefinedMenuItem};
use tauri::tray::TrayIconBuilder;
use tauri::{AppHandle, Wry};
use tauri_plugin_notification::NotificationExt;

const DEFAULT_STATUS_URL: &str = "http://127.0.0.1:8092/status";
const POLL_INTERVAL: Duration = Duration::from_secs(5);
/// How long a block event keeps the tray in "Blocked" before it settles back
/// to "Protected" — a simple time-window rather than an explicit ack click,
/// since there's no tray window to click into yet (menu items only).
const BLOCK_DISPLAY_WINDOW_MS: u64 = 30_000;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum TrayState {
    Protected,
    Disconnected,
    Blocked,
}

impl TrayState {
    fn label(self) -> &'static str {
        match self {
            TrayState::Protected => "Protected",
            TrayState::Disconnected => "Disconnected",
            TrayState::Blocked => "Blocked (recent policy block)",
        }
    }
}

#[derive(Debug, Deserialize)]
struct BlockEvent {
    provider: String,
    reason: String,
    unix_ms: u64,
}

#[derive(Debug, Deserialize)]
struct StatusSnapshot {
    connected: bool,
    last_block: Option<BlockEvent>,
}

fn status_url() -> String {
    std::env::var("AISPM_STATUS_URL").unwrap_or_else(|_| DEFAULT_STATUS_URL.to_string())
}

fn now_unix_ms() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_millis() as u64)
        .unwrap_or(0)
}

fn main() {
    tracing_subscriber::fmt()
        .with_env_filter(
            tracing_subscriber::EnvFilter::try_from_default_env()
                .unwrap_or_else(|_| tracing_subscriber::EnvFilter::new("info")),
        )
        .init();

    tauri::Builder::default()
        .plugin(tauri_plugin_notification::init())
        .setup(|app| {
            let status_item = MenuItem::with_id(
                app,
                "status",
                TrayState::Disconnected.label(),
                false,
                None::<&str>,
            )?;
            let quit_item = MenuItem::with_id(app, "quit", "Quit", true, None::<&str>)?;
            let menu = Menu::with_items(
                app,
                &[
                    &status_item,
                    &PredefinedMenuItem::separator(app)?,
                    &quit_item,
                ],
            )?;

            let tray = TrayIconBuilder::with_id("agent-status")
                .menu(&menu)
                .tooltip("AI-SPM Agent — starting…")
                .icon(app.default_window_icon().cloned().expect(
                    "default window icon missing — check tauri.conf.json bundle.icon paths",
                ))
                .on_menu_event(|app, event| {
                    if event.id().as_ref() == "quit" {
                        app.exit(0);
                    }
                })
                .build(app)?;

            let handle = app.handle().clone();
            tauri::async_runtime::spawn(poll_loop(handle, tray, status_item));

            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running agent-tray");
}

async fn poll_loop(app: AppHandle, tray: tauri::tray::TrayIcon<Wry>, status_item: MenuItem<Wry>) {
    let client = match reqwest::Client::builder()
        .timeout(Duration::from_secs(3))
        .build()
    {
        Ok(c) => c,
        Err(err) => {
            tracing::error!(error = %err, "failed to build HTTP client — tray will stay Disconnected");
            return;
        }
    };
    let url = status_url();
    tracing::info!(%url, "agent-tray polling agent status");

    // Baseline against whatever block is already on record when the tray starts,
    // so a block from before the tray launched doesn't fire a notification the
    // first time it's observed — only genuinely new blocks should notify.
    let last_seen_block_ms = Arc::new(Mutex::new(None::<u64>));
    let mut primed = false;

    let mut interval = tokio::time::interval(POLL_INTERVAL);
    loop {
        interval.tick().await;

        let snapshot: Option<StatusSnapshot> = match client.get(&url).send().await {
            Ok(resp) => resp.json().await.ok(),
            Err(err) => {
                tracing::debug!(error = %err, "status poll failed — treating as disconnected");
                None
            }
        };

        let state = classify(&snapshot);
        let _ = status_item.set_text(state.label());
        let _ = tray.set_tooltip(Some(format!("AI-SPM Agent — {}", state.label())));

        if let Some(block) = snapshot.as_ref().and_then(|s| s.last_block.as_ref()) {
            let mut last_seen = last_seen_block_ms.lock().expect("lock poisoned");
            let is_new = last_seen.map(|seen| block.unix_ms > seen).unwrap_or(true);
            *last_seen = Some(block.unix_ms);

            if is_new && primed {
                notify_block(&app, block);
            }
        }
        primed = true;
    }
}

fn classify(snapshot: &Option<StatusSnapshot>) -> TrayState {
    let Some(snapshot) = snapshot else {
        return TrayState::Disconnected;
    };
    if !snapshot.connected {
        return TrayState::Disconnected;
    }
    match &snapshot.last_block {
        Some(block) if now_unix_ms().saturating_sub(block.unix_ms) < BLOCK_DISPLAY_WINDOW_MS => {
            TrayState::Blocked
        }
        _ => TrayState::Protected,
    }
}

fn notify_block(app: &AppHandle, block: &BlockEvent) {
    if let Err(err) = app
        .notification()
        .builder()
        .title("AI-SPM: request blocked")
        .body(format!("{}: {}", block.provider, block.reason))
        .show()
    {
        tracing::warn!(error = %err, "failed to show block notification");
    }
}
