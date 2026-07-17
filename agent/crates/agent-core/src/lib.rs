//! AI-SPM endpoint agent core library.
//!
//! Provides local HTTP proxy interception, gateway connector, heartbeat, and configuration.

pub mod config;
pub mod endpoint_setup;
pub mod gateway;
pub mod heartbeat;
pub mod local_api;
pub mod network_setup;
pub mod proxy;

pub use config::Config;
pub use gateway::GatewayClient;
pub use proxy::ensure_crypto_provider;
