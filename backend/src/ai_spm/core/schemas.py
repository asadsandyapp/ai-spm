from datetime import datetime
from uuid import UUID

from pydantic import AliasChoices, BaseModel, ConfigDict, EmailStr, Field


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
    subscription_status: str | None = None
    onboarding_step: str | None = None
    plan: str | None = None
    console_access: bool = False
    entitlements: dict | None = None

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
    # Tenant-admin investigation (web MITM): may contain PII.
    original_content: str | None = None
    pii_entities: list[str] = Field(default_factory=list)
    pii_hit_count: int = 0
    source: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class WebAuditRequest(BaseModel):
    """Endpoint web-MITM audit — human prompt text (not API JSON chunks)."""

    provider: str = Field(default="chatgpt", max_length=64)
    model: str = Field(default="web-ui", max_length=128)
    masked_content: str = Field(..., min_length=1, max_length=8000)
    # Unmasked user prompt for tenant-admin Threat/Audit review.
    original_content: str | None = Field(default=None, max_length=8000)
    pii_entities: list[str] = Field(default_factory=list)
    pii_hit_count: int = Field(default=0, ge=0)
    source: str = Field(default="web_mitm", max_length=64)


class WebAuditResponse(BaseModel):
    audit_event_id: UUID
    event_type: str


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
    plan: str = "starter"
    subscription_status: str = "incomplete"
    current_period_end: datetime | None = None
    trial_ends_at: datetime | None = None
    has_stripe_customer: bool = False


class TenantDetailResponse(TenantListItem):
    prompts_today: int = 0
    max_agents: int | None = 0
    max_prompts_per_day: int = 0
    max_prompts_per_month: int | None = None
    max_users: int | None = None
    user_count: int = 0
    audit_retention_days: int | None = None
    billing_interval: str = "month"
    cancel_at_period_end: bool = False
    stripe_customer_id: str | None = None
    stripe_subscription_id: str | None = None
    expires_at: datetime | None = None
    past_due_since: datetime | None = None
    onboarding_step: str | None = None


class PlatformUserResponse(BaseModel):
    id: UUID
    email: str
    full_name: str
    role: str
    is_active: bool = True
    last_login_at: datetime | None = None

    model_config = {"from_attributes": True}


class UpdateProfileRequest(BaseModel):
    full_name: str = Field(..., min_length=1, max_length=255)
    email: EmailStr | None = None


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=12, max_length=128)


class PlatformLoginRequest(BaseModel):
    email: EmailStr
    password: str


class SuspendTenantRequest(BaseModel):
    reason: str = Field(..., min_length=3, max_length=500)


class UsageResponse(BaseModel):
    agent_count: int
    prompts_today: int
    prompts_this_month: int = 0
    max_agents: int
    max_prompts_per_day: int
    max_prompts_per_month: int = 0
    plan: str
    status: str | None = None
    onboarding_step: str | None = None
    max_agents_unlimited: bool = False
    prompts_unlimited: bool = False
    audit_retention_days: int = 7


class ContactSalesRequest(BaseModel):
    """Accept both live Docker field names and commercial schema aliases."""

    model_config = ConfigDict(populate_by_name=True)

    company_name: str = Field(..., min_length=2, max_length=255)
    contact_name: str = Field(..., min_length=2, max_length=255)
    email: EmailStr = Field(
        ...,
        validation_alias=AliasChoices("email", "contact_email"),
    )
    phone: str | None = Field(None, max_length=64)
    estimated_agents: int | None = Field(
        None,
        ge=1,
        le=1_000_000,
        validation_alias=AliasChoices("estimated_agents", "estimated_seats"),
    )
    message: str | None = Field(None, max_length=4000)


class ContactSalesResponse(BaseModel):
    id: UUID
    message: str = "Thanks — our team will contact you shortly."


class SalesLeadResponse(BaseModel):
    id: UUID
    company_name: str
    contact_name: str
    email: str
    phone: str | None
    estimated_agents: int | None
    message: str | None
    status: str
    org_id: UUID | None
    notes: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class AssignPlanRequest(BaseModel):
    plan: str = Field(..., pattern="^(starter|professional|enterprise)$")
    status: str | None = Field(default=None)
    max_agents: int | None = Field(None, ge=0)
    max_users: int | None = Field(None, ge=0)
    max_prompts_per_day: int | None = Field(None, ge=0)
    max_prompts_per_month: int | None = Field(None, ge=0)
    audit_retention_days: int | None = Field(None, ge=1)
    activate: bool = True


class UpdateLeadRequest(BaseModel):
    status: str = Field(..., pattern="^(new|contacted|won|lost)$")
    notes: str | None = None


class DashboardMetricsResponse(BaseModel):
    prompts_24h: int
    blocks_24h: int
    pii_detections_24h: int
    threats_24h: int
    agents_total: int
    agents_online: int
    security_score: int
    daily_activity: list[dict]


class ReportNamedCount(BaseModel):
    name: str
    count: int


class ReportDailyPoint(BaseModel):
    date: str
    total: int
    prompts: int
    blocks: int
    pii: int
    threats: int
    policy_violations: int


class ReportFilterOptions(BaseModel):
    event_types: list[str] = Field(default_factory=list)
    providers: list[str] = Field(default_factory=list)
    devices: list[str] = Field(default_factory=list)
    entities: list[str] = Field(default_factory=list)


class ReportSummaryResponse(BaseModel):
    days: int
    period_start: str
    period_end: str
    total_events: int
    prompts: int
    blocks: int
    pii_detections: int
    threats: int
    policy_violations: int
    prompt_blocked: int
    block_rate_pct: float
    pii_rate_pct: float
    security_score: int
    agents_total: int
    agents_online: int
    agents_offline: int
    agents_pending: int
    agents_revoked: int
    policies_active: int
    avg_daily_events: float
    peak_day: str | None = None
    peak_day_count: int = 0
    daily_activity: list[ReportDailyPoint]
    by_event_type: list[ReportNamedCount]
    by_provider: list[ReportNamedCount]
    by_device: list[ReportNamedCount]
    by_entity: list[ReportNamedCount]
    by_source: list[ReportNamedCount]
    filter_options: ReportFilterOptions


class ThreatEventResponse(BaseModel):
    id: str
    event_type: str
    severity: str
    masked_content: str
    original_content: str | None = None
    metadata: dict
    pii_entities: list[str] = Field(default_factory=list)
    pii_hit_count: int = 0
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


class PiiDetectionPolicyResponse(BaseModel):
    id: str
    name: str
    category: str
    description: str
    mask: str
    detectable: bool
    enabled: bool
    status: str


class UpdatePiiDetectionRequest(BaseModel):
    enabled: bool


class AgentPiiPolicyResponse(BaseModel):
    """Synced to endpoint agents / web MITM (enabled detectable entities only)."""

    enabled_entities: list[str]
    action: str = "mask"


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
