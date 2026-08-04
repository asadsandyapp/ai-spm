"""Enterprise severity classification for audit / threat-feed events.

Severity is derived from event type, threat-engine output, PII entity
sensitivity tiers, and detection volume — not a flat map of event_type → medium.
"""

from __future__ import annotations

from typing import Any, Literal

from ai_spm.domain.enums import AuditEventType
from ai_spm.services.pii_catalog import ENTITY_ALIASES, normalize_entity_id

Severity = Literal["low", "medium", "high"]

SEVERITY_RANK: dict[str, int] = {"low": 1, "medium": 2, "high": 3}

# Regulated identifiers, secrets, and PHI — immediate high severity.
CRITICAL_PII_ENTITIES: frozenset[str] = frozenset(
    {
        "US_SSN",
        "CNIC",
        "CREDIT_CARD",
        "IBAN",
        "PASSPORT_NUMBER",
        "TAX_ID",
        "LOGIN_CREDENTIALS",
        "BIOMETRIC_ID",
        "FACIAL_RECOGNITION_DATA",
        "HEALTH_INSURANCE_ID",
        "MEDICAL_INFO",
        "MOTHERS_MAIDEN_NAME",
    }
)

# Direct contact / identity data — medium by default.
MEDIUM_PII_ENTITIES: frozenset[str] = frozenset(
    {
        "EMAIL_ADDRESS",
        "PHONE_NUMBER",
        "PERSON_NAME",
        "STREET_ADDRESS",
        "DRIVER_LICENSE",
        "DATE_OF_BIRTH",
        "PLACE_OF_BIRTH",
        "IP_ADDRESS",
        "MAC_ADDRESS",
        "GEOLOCATION",
        "DEVICE_COOKIE_ID",
        "VEHICLE_PLATE",
        "MEMBERSHIP_ID",
        "BADGE_ID",
        "PURCHASE_HISTORY",
    }
)

# Soft / contextual attributes — low unless volume escalates.
LOW_PII_ENTITIES: frozenset[str] = frozenset(
    {
        "GENDER",
        "MARITAL_STATUS",
        "ETHNICITY",
        "SEXUAL_ORIENTATION",
        "RELIGIOUS_POLITICAL",
        "EMPLOYMENT",
        "EDUCATION",
        "ONLINE_USERNAME",
        "SOCIAL_HANDLE",
        "PHOTO_VIDEO_ID",
    }
)


def _normalize_severity(value: str | None) -> Severity | None:
    if not value:
        return None
    key = value.strip().lower()
    if key in SEVERITY_RANK:
        return key  # type: ignore[return-value]
    return None


def _max_severity(*values: Severity | None) -> Severity:
    best: Severity = "low"
    for value in values:
        if value and SEVERITY_RANK[value] > SEVERITY_RANK[best]:
            best = value
    return best


def _bump(severity: Severity, steps: int = 1) -> Severity:
    rank = min(3, SEVERITY_RANK[severity] + steps)
    for name, value in SEVERITY_RANK.items():
        if value == rank:
            return name  # type: ignore[return-value]
    return "high"


def _normalize_entities(raw: list[Any] | None) -> list[str]:
    out: list[str] = []
    for item in raw or []:
        if not isinstance(item, str):
            continue
        normalized = normalize_entity_id(item) or ENTITY_ALIASES.get(
            item.strip().upper(), item.strip().upper()
        )
        if normalized:
            out.append(normalized)
    return out


def classify_pii_entities(
    entities: list[str] | None,
    *,
    hit_count: int = 0,
) -> Severity:
    """Classify PII findings by entity sensitivity + volume."""
    normalized = _normalize_entities(entities)
    distinct = set(normalized)
    hits = max(int(hit_count or 0), len(normalized))

    if not distinct and hits <= 0:
        return "low"

    if distinct & CRITICAL_PII_ENTITIES:
        base: Severity = "high"
    elif distinct & MEDIUM_PII_ENTITIES or not distinct:
        # Unknown entity IDs default to medium (safer for enterprise).
        base = "medium"
    elif distinct & LOW_PII_ENTITIES and not (
        distinct - LOW_PII_ENTITIES - CRITICAL_PII_ENTITIES - MEDIUM_PII_ENTITIES
    ):
        base = "low"
    else:
        base = "medium"

    # Volume / blast-radius escalation.
    if hits >= 15 or len(distinct) >= 8:
        base = _bump(base, 2 if base == "low" else 1)
    elif hits >= 5 or len(distinct) >= 4:
        base = _bump(base)

    return base


def classify_event_severity(
    event_type: AuditEventType | str,
    metadata: dict[str, Any] | None = None,
) -> Severity:
    """Compute low / medium / high for an audit event.

    Prefer an explicit ``threat_severity`` from the scanner when present; otherwise
    derive from event type + PII payload. Result is always one of low|medium|high.
    """
    meta = metadata or {}
    if isinstance(event_type, AuditEventType):
        et = event_type
    else:
        try:
            et = AuditEventType(str(event_type))
        except ValueError:
            et = AuditEventType.PROMPT_SUBMITTED

    stored = _normalize_severity(
        meta.get("severity") if isinstance(meta.get("severity"), str) else None
    )
    threat_sev = _normalize_severity(
        meta.get("threat_severity")
        if isinstance(meta.get("threat_severity"), str)
        else None
    )

    entities = meta.get("pii_entities")
    if not isinstance(entities, list):
        entities = []
    hit_count = int(meta.get("pii_hit_count") or 0)
    pii_sev = classify_pii_entities(entities, hit_count=hit_count)

    fail_closed = bool(meta.get("fail_closed"))
    block_code = str(meta.get("block_code") or "")

    if et == AuditEventType.THREAT_DETECTED:
        # Inbound injection / jailbreak is high unless scanner says otherwise.
        return _max_severity(threat_sev or "high", pii_sev)

    if et == AuditEventType.PROMPT_BLOCKED:
        if fail_closed or block_code in {"SCANNER_ERROR", "THREAT_DETECTED", "RESPONSE_THREAT"}:
            return "high"
        return _max_severity("medium", pii_sev, threat_sev)

    if et == AuditEventType.POLICY_VIOLATION:
        # Governance denials are medium; escalate if also carrying critical PII.
        return _max_severity("medium", pii_sev if pii_sev == "high" else None)

    if et == AuditEventType.PII_DETECTED:
        return pii_sev

    if et == AuditEventType.PROMPT_SUBMITTED:
        return "low"

    # Fallback for other lifecycle events.
    return stored or "low"


def attach_severity(metadata: dict[str, Any], event_type: AuditEventType | str) -> dict[str, Any]:
    """Return a copy of metadata with ``severity`` (and factors) set."""
    meta = dict(metadata or {})
    # Avoid using a stale stub severity while computing.
    meta.pop("severity", None)
    severity = classify_event_severity(event_type, meta)
    meta["severity"] = severity
    factors: list[str] = [f"event:{event_type if isinstance(event_type, str) else event_type.value}"]
    if meta.get("threat_severity"):
        factors.append(f"threat:{meta['threat_severity']}")
    entities = meta.get("pii_entities") or []
    if entities:
        factors.append(f"pii_types:{len(set(str(e) for e in entities))}")
    if meta.get("pii_hit_count"):
        factors.append(f"hits:{meta['pii_hit_count']}")
    if meta.get("fail_closed"):
        factors.append("fail_closed")
    meta["severity_factors"] = factors
    return meta
