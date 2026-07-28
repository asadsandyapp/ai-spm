use serde::{Deserialize, Serialize};

/// Incoming and forwarded request body. Only the `prompt` field is processed.
#[derive(Debug, Deserialize, Serialize)]
pub struct ProxyRequest {
    pub prompt: String,
}
