use axum::{
    body::Body,
    extract::{Json, State},
    http::{HeaderMap, StatusCode},
    response::{IntoResponse, Response},
};
use reqwest::Client;
use std::sync::Arc;
use tracing::{info, warn};

use crate::config::Config;
use crate::masker::{count_emails, mask_emails};
use crate::models::ProxyRequest;

/// Shared application state passed to request handlers.
pub struct AppState {
    pub client: Client,
    pub config: Config,
}

/// `POST /proxy` — mask emails in the prompt and forward to the upstream AI service.
pub async fn proxy_handler(
    State(state): State<Arc<AppState>>,
    body: Result<Json<ProxyRequest>, axum::extract::rejection::JsonRejection>,
) -> Response {
    let Json(request) = match body {
        Ok(json) => json,
        Err(_) => {
            return (StatusCode::BAD_REQUEST, "Invalid JSON").into_response();
        }
    };

    info!("Request received");

    let email_count = count_emails(&request.prompt);
    info!(email_count, "Number of emails detected");

    let masked_request = ProxyRequest {
        prompt: mask_emails(&request.prompt),
    };

    info!("Request forwarded");

    let upstream_response = match state
        .client
        .post(&state.config.upstream_url)
        .json(&masked_request)
        .send()
        .await
    {
        Ok(response) => response,
        Err(err) => {
            warn!(error = %err, "Upstream unavailable");
            return (StatusCode::BAD_GATEWAY, "Upstream unavailable").into_response();
        }
    };

    info!("Response received");

    let status = StatusCode::from_u16(upstream_response.status().as_u16())
        .unwrap_or(StatusCode::INTERNAL_SERVER_ERROR);

    let headers: HeaderMap = upstream_response
        .headers()
        .iter()
        .map(|(name, value)| (name.clone(), value.clone()))
        .collect();

    let body_bytes = match upstream_response.bytes().await {
        Ok(bytes) => bytes,
        Err(err) => {
            warn!(error = %err, "Failed to read upstream response body");
            return (StatusCode::INTERNAL_SERVER_ERROR, "Internal proxy error").into_response();
        }
    };

    let mut response = Response::new(Body::from(body_bytes));
    *response.status_mut() = status;
    *response.headers_mut() = headers;
    response
}
