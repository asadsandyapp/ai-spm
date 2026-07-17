from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class SignupRequest(BaseModel):
    company_name: str = Field(..., min_length=2, max_length=255)
    admin_email: EmailStr
    admin_password: str = Field(..., min_length=12, max_length=128)
    admin_full_name: str = Field(..., min_length=2, max_length=255)


class SignupResponse(BaseModel):
    org_id: UUID
    slug: str
    message: str = "Verification email sent"
    # Present only in development/debug so local demos can verify without email.
    verification_token: str | None = None


class VerifyEmailResponse(BaseModel):
    org_id: UUID
    slug: str
    status: str
    message: str
    # Shown once on successful verify — required for agent install (AISPM_ORG_TOKEN).
    org_token: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class UserResponse(BaseModel):
    id: UUID
    email: str
    full_name: str
    role: str
    org_id: UUID

    model_config = {"from_attributes": True}


class AgentResponse(BaseModel):
    id: UUID
    org_id: UUID
    hostname: str
    status: str
    os_version: str | None
    agent_version: str | None
    last_heartbeat_at: datetime | None

    model_config = {"from_attributes": True}


class EnrollmentInfoResponse(BaseModel):
    org_id: UUID
    org_name: str
    org_slug: str
    gateway_url: str
    has_token: bool
    installer_linux_ready: bool


class OrgTokenRotateResponse(BaseModel):
    org_id: UUID
    org_token: str
    message: str = (
        "Store this org_token securely. It is shown once — required for agent enrollment."
    )


class AgentRegisterRequest(BaseModel):
    hostname: str = Field(..., min_length=1, max_length=255)
    os_version: str | None = None
    agent_version: str | None = None
    org_token: str = Field(..., min_length=32)
    csr_pem: str | None = None


class AgentRegisterWithCertResponse(AgentResponse):
    certificate_pem: str
    private_key_pem: str
    ca_certificate_pem: str
    cert_expires_at: str


class AgentUpdateCheckResponse(BaseModel):
    current_version: str
    latest_version: str
    update_available: bool
    download_url: str | None = None


class AuditEventResponse(BaseModel):
    id: UUID
    event_type: str
    agent_id: UUID | None
    hostname: str | None = None
    provider: str | None = None
    masked_content: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class PromptRequest(BaseModel):
    provider: str = "openai"
    model: str = "gpt-4o-mini"
    messages: list[dict[str, str]]
    max_tokens: int = 1024
    # When true, run policy/threat/PII scans only — do not call the LLM.
    # Used by the endpoint agent HTTPS MITM proxy to inspect browser traffic
    # before forwarding the (possibly masked) request to the real provider.
    inspect_only: bool = False


class PromptResponse(BaseModel):
    decision: str
    masked_messages: list[dict[str, str]] | None = None
    response_content: str | None = None
    audit_event_id: UUID | None = None
    blocked_reason: str | None = None
    block_code: str | None = None
    pii_masked: list[str] | None = None


class PolicyResponse(BaseModel):
    id: UUID
    name: str
    description: str | None
    rules: dict
    is_default: bool
    is_active: bool

    model_config = {"from_attributes": True}


class TenantListItem(BaseModel):
    id: UUID
    slug: str
    name: str
    status: str
    created_at: datetime
    agent_count: int = 0
    plan: str = "free"


class TenantDetailResponse(TenantListItem):
    prompts_today: int = 0
    max_agents: int = 0
    max_prompts_per_day: int = 0


class PlatformLoginRequest(BaseModel):
    email: EmailStr
    password: str


class SuspendTenantRequest(BaseModel):
    reason: str = Field(..., min_length=3, max_length=500)


class UsageResponse(BaseModel):
    agent_count: int
    prompts_today: int
    max_agents: int
    max_prompts_per_day: int
    plan: str


class DashboardMetricsResponse(BaseModel):
    prompts_24h: int
    blocks_24h: int
    pii_detections_24h: int
    threats_24h: int
    agents_total: int
    agents_online: int
    security_score: int
    daily_activity: list[dict]


class ThreatEventResponse(BaseModel):
    id: str
    event_type: str
    severity: str
    masked_content: str
    metadata: dict
    created_at: str
    agent_id: str | None = None
    hostname: str | None = None
    provider: str | None = None


class CreatePolicyRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=255)
    description: str | None = None
    rules: dict = Field(default_factory=dict)
    is_default: bool = False


class UpdatePolicyRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    rules: dict | None = None
    is_active: bool | None = None


class CreateUserRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=12)
    full_name: str = Field(..., min_length=2)
    role: str = "viewer"


class LLMConfigRequest(BaseModel):
    provider: str = "openai"
    api_key: str = Field(..., min_length=10)
    is_active: bool = True


class LLMConfigResponse(BaseModel):
    id: UUID
    provider: str
    is_active: bool


class AuditExportResponse(BaseModel):
    format: str
    row_count: int
    download_url: str
