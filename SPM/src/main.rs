mod config;
mod masker;
mod models;
mod proxy;

use std::sync::Arc;

use axum::{routing::post, Router};
use tracing::info;
use tracing_subscriber::{layer::SubscriberExt, util::SubscriberInitExt};

use config::Config;
use proxy::{proxy_handler, AppState};

#[tokio::main]
async fn main() {
    tracing_subscriber::registry()
        .with(
            tracing_subscriber::EnvFilter::try_from_default_env()
                .unwrap_or_else(|_| "info".into()),
        )
        .with(tracing_subscriber::fmt::layer())
        .init();

    let config = match Config::from_env() {
        Ok(config) => config,
        Err(message) => {
            eprintln!("Configuration error: {message}");
            std::process::exit(1);
        }
    };

    let listen_addr = config.listen_addr.clone();
    let state = Arc::new(AppState {
        client: reqwest::Client::new(),
        config,
    });

    let app = Router::new()
        .route("/proxy", post(proxy_handler))
        .with_state(state);

    let listener = tokio::net::TcpListener::bind(&listen_addr)
        .await
        .expect("failed to bind listen address");

    info!(%listen_addr, "Reverse proxy listening");

    axum::serve(listener, app)
        .await
        .expect("server error");
}
