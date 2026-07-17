import enum


class OrganizationStatus(str, enum.Enum):
    PENDING = "pending"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    DELETED = "deleted"


class SubscriptionPlan(str, enum.Enum):
    FREE = "free"
    PRO = "pro"
    ENTERPRISE = "enterprise"


class SubscriptionStatus(str, enum.Enum):
    TRIALING = "trialing"
    ACTIVE = "active"
    PAST_DUE = "past_due"
    CANCELED = "canceled"
    SUSPENDED = "suspended"


class UserRole(str, enum.Enum):
    SUPER_ADMIN = "super_admin"
    SECURITY_ADMIN = "security_admin"
    AUDITOR = "auditor"
    VIEWER = "viewer"


class PlatformRole(str, enum.Enum):
    PLATFORM_SUPER = "platform_super"
    PLATFORM_SUPPORT = "platform_support"
    PLATFORM_BILLING = "platform_billing"


class AgentStatus(str, enum.Enum):
    PENDING = "pending"
    ONLINE = "online"
    OFFLINE = "offline"
    REVOKED = "revoked"


class AuditEventType(str, enum.Enum):
    PROMPT_SUBMITTED = "prompt_submitted"
    PROMPT_BLOCKED = "prompt_blocked"
    POLICY_VIOLATION = "policy_violation"
    PII_DETECTED = "pii_detected"
    THREAT_DETECTED = "threat_detected"
    AGENT_REGISTERED = "agent_registered"
    AGENT_HEARTBEAT = "agent_heartbeat"
    ADMIN_LOGIN = "admin_login"
    CONFIG_CHANGED = "config_changed"


class PolicyAction(str, enum.Enum):
    ALLOW = "allow"
    BLOCK = "block"
    ALERT = "alert"


class PromptDecision(str, enum.Enum):
    ALLOWED = "allowed"
    BLOCKED = "blocked"
    MASKED = "masked"
