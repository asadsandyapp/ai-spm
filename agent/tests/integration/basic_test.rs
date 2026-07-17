use agent_core::proxy::{should_intercept, DEFAULT_MITM_DOMAINS};
use agent_core::Config;
use uuid::Uuid;

#[test]
fn mitm_domains_list_is_non_empty() {
    assert!(!DEFAULT_MITM_DOMAINS.is_empty());
    assert!(DEFAULT_MITM_DOMAINS.contains(&"api.openai.com"));
    assert!(DEFAULT_MITM_DOMAINS.contains(&"api.anthropic.com"));
}

#[test]
fn should_intercept_ai_api_hosts() {
    assert!(should_intercept("api.openai.com"));
    assert!(should_intercept("api.anthropic.com"));
    assert!(!should_intercept("google.com"));
}

#[test]
fn config_loads_from_environment() {
    let org_id = Uuid::new_v4();
    let token = "a".repeat(32);

    std::env::set_var("AISPM_GATEWAY_URL", "http://127.0.0.1:8000");
    std::env::set_var("AISPM_ORG_TOKEN", &token);
    std::env::set_var("AISPM_ORG_ID", org_id.to_string());
    std::env::set_var("AISPM_PROXY_LISTEN", "127.0.0.1:18080");

    let config = Config::load().expect("config should load");
    assert_eq!(config.gateway_url, "http://127.0.0.1:8000");
    assert_eq!(config.org_token, token);
    assert_eq!(config.org_id, org_id);
    assert_eq!(config.proxy_listen.port(), 18080);

    std::env::remove_var("AISPM_GATEWAY_URL");
    std::env::remove_var("AISPM_ORG_TOKEN");
    std::env::remove_var("AISPM_ORG_ID");
    std::env::remove_var("AISPM_PROXY_LISTEN");
}
