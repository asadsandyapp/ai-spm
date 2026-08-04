//! In-process, shared view of agent health for local UIs (the tray app) to poll
//! over `local_api`'s `GET /status`. Updated by the heartbeat loop (connectivity)
//! and the MITM/inspect paths (policy blocks). Not persisted — resets on restart,
//! which is fine since it only feeds a point-in-time tray icon, not audit history
//! (that lives in the gateway's append-only audit log).

use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, RwLock};
use std::time::{SystemTime, UNIX_EPOCH};

use serde::Serialize;

#[derive(Debug, Default)]
pub struct AgentStatus {
    connected: AtomicBool,
    last_block: RwLock<Option<BlockEvent>>,
}

pub type SharedAgentStatus = Arc<AgentStatus>;

#[derive(Debug, Clone, Serialize)]
pub struct BlockEvent {
    pub provider: String,
    pub reason: String,
    pub unix_ms: u64,
}

#[derive(Debug, Clone, Serialize)]
pub struct StatusSnapshot {
    pub connected: bool,
    pub last_block: Option<BlockEvent>,
}

impl AgentStatus {
    pub fn shared() -> SharedAgentStatus {
        Arc::new(Self::default())
    }

    pub fn set_connected(&self, connected: bool) {
        self.connected.store(connected, Ordering::Relaxed);
    }

    pub fn is_connected(&self) -> bool {
        self.connected.load(Ordering::Relaxed)
    }

    pub fn record_block(&self, provider: impl Into<String>, reason: impl Into<String>) {
        let unix_ms = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .map(|d| d.as_millis() as u64)
            .unwrap_or(0);
        let event = BlockEvent {
            provider: provider.into(),
            reason: reason.into(),
            unix_ms,
        };
        // Poisoning here would mean a panic elsewhere while holding the lock;
        // recovering the inner value keeps tray polling alive rather than
        // taking the whole status feed down over a single bad write.
        match self.last_block.write() {
            Ok(mut guard) => *guard = Some(event),
            Err(poisoned) => *poisoned.into_inner() = Some(event),
        }
    }

    pub fn snapshot(&self) -> StatusSnapshot {
        let last_block = match self.last_block.read() {
            Ok(guard) => guard.clone(),
            Err(poisoned) => poisoned.into_inner().clone(),
        };
        StatusSnapshot {
            connected: self.is_connected(),
            last_block,
        }
    }
}
