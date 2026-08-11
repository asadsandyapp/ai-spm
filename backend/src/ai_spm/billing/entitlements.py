"""Single source of truth for commercial plan limits and feature entitlements.

Plan capacity is based on max_agents (protected endpoints), never seats/users.
max_agents / max_prompts_per_month of 0 means unlimited.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ai_spm.domain.enums import SubscriptionPlan

# Feature keys enforced by backend (frontend mirrors for UX only).
FEATURE_THREAT_DETECTION = "threat_detection"
FEATURE_ADVANCED_POLICY = "advanced_policy"
FEATURE_POLICY_BUILDER = "policy_builder"
FEATURE_MULTI_PROVIDER = "multi_provider"
FEATURE_HA_GATEWAY = "ha_gateway"
FEATURE_CUSTOM_DASHBOARDS = "custom_dashboards"
FEATURE_AUDIT_EXPORT = "audit_export"
FEATURE_NLP_PII = "nlp_pii"
FEATURE_CUSTOM_ENTITIES = "custom_entities"
FEATURE_CUSTOM_MODEL_TRAINING = "custom_model_training"
FEATURE_API_POLICY_INTEGRATION = "api_policy_integration"
FEATURE_TOPIC_BLOCKING = "topic_blocking"

PAST_DUE_GRACE_DAYS = 7

# Stripe price lookup_keys → plan
STRIPE_LOOKUP_KEYS: dict[str, SubscriptionPlan] = {
    "starter_monthly": SubscriptionPlan.STARTER,
    "professional_monthly": SubscriptionPlan.PROFESSIONAL,
    "enterprise_monthly": SubscriptionPlan.ENTERPRISE,
    # Legacy keys during migration
    "free": SubscriptionPlan.STARTER,
    "pro": SubscriptionPlan.PROFESSIONAL,
    "enterprise": SubscriptionPlan.ENTERPRISE,
}


@dataclass(frozen=True)
class PlanDefinition:
    plan: SubscriptionPlan
    display_name: str
    audience: str
    price_monthly_usd: int
    max_agents: int  # 0 = unlimited
    max_prompts_per_month: int  # 0 = unlimited
    audit_retention_days: int
    features: frozenset[str]
    stripe_lookup_key: str
    contact_sales: bool = False
    support: str = "email"
    gateway: str = "Single provider"
    pii_dlp: str = "Basic (regex)"
    policy_engine: str = "Standard RBAC"
    dashboard: str = "Basic metrics"
    threat_detection_label: str = "Not included"
    audit_label: str = "7-day retention"

    @property
    def max_prompts_per_day(self) -> int:
        """Derived daily ceiling for the existing UsageDaily counter."""
        if self.max_prompts_per_month <= 0:
            return 0  # unlimited
        return max(1, (self.max_prompts_per_month + 29) // 30)

    def feature_map(self) -> dict[str, bool]:
        return {
            FEATURE_THREAT_DETECTION: FEATURE_THREAT_DETECTION in self.features,
            FEATURE_ADVANCED_POLICY: FEATURE_ADVANCED_POLICY in self.features,
            FEATURE_POLICY_BUILDER: FEATURE_POLICY_BUILDER in self.features,
            FEATURE_MULTI_PROVIDER: FEATURE_MULTI_PROVIDER in self.features,
            FEATURE_HA_GATEWAY: FEATURE_HA_GATEWAY in self.features,
            FEATURE_CUSTOM_DASHBOARDS: FEATURE_CUSTOM_DASHBOARDS in self.features,
            FEATURE_AUDIT_EXPORT: FEATURE_AUDIT_EXPORT in self.features,
            FEATURE_NLP_PII: FEATURE_NLP_PII in self.features,
            FEATURE_CUSTOM_ENTITIES: FEATURE_CUSTOM_ENTITIES in self.features,
            FEATURE_CUSTOM_MODEL_TRAINING: FEATURE_CUSTOM_MODEL_TRAINING in self.features,
            FEATURE_API_POLICY_INTEGRATION: FEATURE_API_POLICY_INTEGRATION in self.features,
            FEATURE_TOPIC_BLOCKING: FEATURE_TOPIC_BLOCKING in self.features,
        }

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "plan": self.plan.value,
            "display_name": self.display_name,
            "audience": self.audience,
            "price_monthly_usd": self.price_monthly_usd,
            "max_agents": self.max_agents,
            "max_agents_label": "Unlimited" if self.max_agents == 0 else f"Up to {self.max_agents}",
            "max_prompts_per_month": self.max_prompts_per_month,
            "audit_retention_days": self.audit_retention_days,
            "contact_sales": self.contact_sales,
            "support": self.support,
            "gateway": self.gateway,
            "pii_dlp": self.pii_dlp,
            "policy_engine": self.policy_engine,
            "dashboard": self.dashboard,
            "threat_detection": self.threat_detection_label,
            "audit_logging": self.audit_label,
            "features": self.feature_map(),
            "stripe_lookup_key": self.stripe_lookup_key,
        }


_STARTER_FEATURES = frozenset()
_PRO_FEATURES = frozenset(
    {
        FEATURE_THREAT_DETECTION,
        FEATURE_ADVANCED_POLICY,
        FEATURE_POLICY_BUILDER,
        FEATURE_MULTI_PROVIDER,
        FEATURE_NLP_PII,
        FEATURE_CUSTOM_ENTITIES,
        FEATURE_TOPIC_BLOCKING,
    }
)
_ENTERPRISE_FEATURES = frozenset(
    {
        *_PRO_FEATURES,
        FEATURE_HA_GATEWAY,
        FEATURE_CUSTOM_DASHBOARDS,
        FEATURE_AUDIT_EXPORT,
        FEATURE_CUSTOM_MODEL_TRAINING,
        FEATURE_API_POLICY_INTEGRATION,
    }
)

PLAN_CATALOG: dict[SubscriptionPlan, PlanDefinition] = {
    SubscriptionPlan.STARTER: PlanDefinition(
        plan=SubscriptionPlan.STARTER,
        display_name="Starter",
        audience="Small Teams / Pilot",
        price_monthly_usd=1500,
        max_agents=25,
        max_prompts_per_month=50_000,
        audit_retention_days=7,
        features=_STARTER_FEATURES,
        stripe_lookup_key="starter_monthly",
        support="Email support",
        gateway="Single provider",
        pii_dlp="Basic (regex patterns)",
        policy_engine="Standard RBAC",
        dashboard="Basic metrics",
        threat_detection_label="Not included",
        audit_label="7-day retention",
    ),
    SubscriptionPlan.PROFESSIONAL: PlanDefinition(
        plan=SubscriptionPlan.PROFESSIONAL,
        display_name="Professional",
        audience="Mid-Size Companies",
        price_monthly_usd=4500,
        max_agents=150,
        max_prompts_per_month=500_000,
        audit_retention_days=30,
        features=_PRO_FEATURES,
        stripe_lookup_key="professional_monthly",
        support="Business hours support",
        gateway="Multi-provider",
        pii_dlp="Full (NLP + custom entities)",
        policy_engine="Advanced RBAC + topic blocking",
        dashboard="Full analytics + policy builder",
        threat_detection_label="Jailbreak / injection detection",
        audit_label="30-day retention",
    ),
    SubscriptionPlan.ENTERPRISE: PlanDefinition(
        plan=SubscriptionPlan.ENTERPRISE,
        display_name="Enterprise",
        audience="Large Enterprises & MSPs",
        price_monthly_usd=12000,
        max_agents=0,
        max_prompts_per_month=0,
        audit_retention_days=365,
        features=_ENTERPRISE_FEATURES,
        stripe_lookup_key="enterprise_monthly",
        contact_sales=True,
        support="24/7 priority support + SLA",
        gateway="Multi-provider + HA",
        pii_dlp="Full + custom model training",
        policy_engine="Granular policies + API integration",
        dashboard="Custom dashboards",
        threat_detection_label="Advanced / 0-day-style protection",
        audit_label="1-year retention + export",
    ),
}

# Back-compat alias used by older call sites
PLAN_LIMITS = {
    plan: (defn.max_agents, defn.max_prompts_per_day, defn.audit_retention_days)
    for plan, defn in PLAN_CATALOG.items()
}


def get_plan(plan: SubscriptionPlan | str) -> PlanDefinition:
    if isinstance(plan, str):
        plan = SubscriptionPlan(plan)
    return PLAN_CATALOG[plan]


def has_feature(plan: SubscriptionPlan | str, feature: str) -> bool:
    return feature in get_plan(plan).features


def is_unlimited(limit: int) -> bool:
    return limit <= 0


def public_plan_catalog() -> list[dict[str, Any]]:
    return [PLAN_CATALOG[p].to_public_dict() for p in (
        SubscriptionPlan.STARTER,
        SubscriptionPlan.PROFESSIONAL,
        SubscriptionPlan.ENTERPRISE,
    )]
