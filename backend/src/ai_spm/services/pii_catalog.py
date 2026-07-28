"""Enterprise PII detection catalog — each entity is a toggleable detection policy.

Canonical entity IDs match Presidio / web-mitm regex names. Admins enable or
disable each detection independently. All catalog entities are ``detectable``
(enforced when Active) via shared gateway + web MITM patterns.
"""

from __future__ import annotations

from typing import Any, TypedDict

# Aliases accepted in legacy seed JSON (`pii.entities` list).
ENTITY_ALIASES: dict[str, str] = {
    "EMAIL": "EMAIL_ADDRESS",
    "PHONE": "PHONE_NUMBER",
    "SSN": "US_SSN",
    "US_SSN": "US_SSN",
    "CREDIT_CARD": "CREDIT_CARD",
    "CNIC": "CNIC",
    "EMAIL_ADDRESS": "EMAIL_ADDRESS",
    "PHONE_NUMBER": "PHONE_NUMBER",
    "DATE_OF_BIRTH": "DATE_OF_BIRTH",
    "IP_ADDRESS": "IP_ADDRESS",
    "IBAN": "IBAN",
    "PASSPORT_NUMBER": "PASSPORT_NUMBER",
    "DRIVER_LICENSE": "DRIVER_LICENSE",
}


class PiiDetectionDef(TypedDict):
    id: str
    name: str
    category: str
    description: str
    mask: str
    detectable: bool
    default_enabled: bool


# Full enterprise catalog (user-facing). Every entry is enforceable when enabled.
PII_CATALOG: list[PiiDetectionDef] = [
    # --- Direct identifiers (implemented) ---
    {
        "id": "EMAIL_ADDRESS",
        "name": "Email address",
        "category": "Direct Identifiers",
        "description": "Personal or work email addresses.",
        "mask": "***@***.com",
        "detectable": True,
        "default_enabled": True,
    },
    {
        "id": "PHONE_NUMBER",
        "name": "Phone number",
        "category": "Direct Identifiers",
        "description": "Home, work, or mobile phone numbers.",
        "mask": "***-***-****",
        "detectable": True,
        "default_enabled": True,
    },
    {
        "id": "US_SSN",
        "name": "Social Security Number (SSN)",
        "category": "Direct Identifiers",
        "description": "US SSN or equivalent national ID patterns.",
        "mask": "***-**-****",
        "detectable": True,
        "default_enabled": True,
    },
    {
        "id": "CNIC",
        "name": "National ID (CNIC)",
        "category": "Direct Identifiers",
        "description": "Pakistan CNIC and similar national ID formats.",
        "mask": "*************",
        "detectable": True,
        "default_enabled": True,
    },
    {
        "id": "CREDIT_CARD",
        "name": "Credit / debit card",
        "category": "Direct Identifiers",
        "description": "Payment card numbers (PAN).",
        "mask": "****-****-****-1234",
        "detectable": True,
        "default_enabled": True,
    },
    {
        "id": "IBAN",
        "name": "Bank account / IBAN",
        "category": "Direct Identifiers",
        "description": "International bank account numbers.",
        "mask": "****IBAN****",
        "detectable": True,
        "default_enabled": False,
    },
    {
        "id": "PASSPORT_NUMBER",
        "name": "Passport number",
        "category": "Direct Identifiers",
        "description": "Passport-style alphanumeric identifiers.",
        "mask": "********",
        "detectable": True,
        "default_enabled": False,
    },
    {
        "id": "DRIVER_LICENSE",
        "name": "Driver’s license",
        "category": "Direct Identifiers",
        "description": "Driver license numbers (common US-style patterns).",
        "mask": "********",
        "detectable": True,
        "default_enabled": False,
    },
    # --- Direct identifiers (contextual / labeled patterns) ---
    {
        "id": "PERSON_NAME",
        "name": "Full name",
        "category": "Direct Identifiers",
        "description": "Labeled names (e.g. “my name is …”, “name: …”).",
        "mask": "[NAME]",
        "detectable": True,
        "default_enabled": False,
    },
    {
        "id": "STREET_ADDRESS",
        "name": "Street address",
        "category": "Direct Identifiers",
        "description": "Street address with street/avenue/road-style suffixes.",
        "mask": "[ADDRESS]",
        "detectable": True,
        "default_enabled": False,
    },
    {
        "id": "TAX_ID",
        "name": "Tax identification number",
        "category": "Direct Identifiers",
        "description": "EIN / TIN / tax IDs (##-#######).",
        "mask": "**-*******",
        "detectable": True,
        "default_enabled": False,
    },
    {
        "id": "HEALTH_INSURANCE_ID",
        "name": "Health insurance policy number",
        "category": "Direct Identifiers",
        "description": "Health plan / member IDs (labeled).",
        "mask": "********",
        "detectable": True,
        "default_enabled": False,
    },
    {
        "id": "VEHICLE_PLATE",
        "name": "Vehicle registration / plate",
        "category": "Direct Identifiers",
        "description": "License plate and vehicle registration (labeled).",
        "mask": "********",
        "detectable": True,
        "default_enabled": False,
    },
    {
        "id": "ONLINE_USERNAME",
        "name": "Online username",
        "category": "Direct Identifiers",
        "description": "Usernames when labeled (username / login name).",
        "mask": "[USERNAME]",
        "detectable": True,
        "default_enabled": False,
    },
    {
        "id": "BIOMETRIC_ID",
        "name": "Biometric identifiers",
        "category": "Direct Identifiers",
        "description": "Fingerprints, facial templates, voiceprints (text references).",
        "mask": "[BIOMETRIC]",
        "detectable": True,
        "default_enabled": False,
    },
    # --- Sensitive / context-specific ---
    {
        "id": "DATE_OF_BIRTH",
        "name": "Date of birth",
        "category": "Sensitive / Context-Specific",
        "description": "Birth dates in common formats.",
        "mask": "**/**/****",
        "detectable": True,
        "default_enabled": False,
    },
    {
        "id": "PLACE_OF_BIRTH",
        "name": "Place of birth",
        "category": "Sensitive / Context-Specific",
        "description": "City or country of birth (labeled).",
        "mask": "[PLACE]",
        "detectable": True,
        "default_enabled": False,
    },
    {
        "id": "MOTHERS_MAIDEN_NAME",
        "name": "Mother’s maiden name",
        "category": "Sensitive / Context-Specific",
        "description": "Maiden name used as a secret or identifier.",
        "mask": "[REDACTED]",
        "detectable": True,
        "default_enabled": False,
    },
    {
        "id": "GENDER",
        "name": "Gender",
        "category": "Sensitive / Context-Specific",
        "description": "Gender when labeled (gender: / sex:).",
        "mask": "[REDACTED]",
        "detectable": True,
        "default_enabled": False,
    },
    {
        "id": "MARITAL_STATUS",
        "name": "Marital status",
        "category": "Sensitive / Context-Specific",
        "description": "Marital status references (labeled).",
        "mask": "[REDACTED]",
        "detectable": True,
        "default_enabled": False,
    },
    {
        "id": "ETHNICITY",
        "name": "Ethnicity or race",
        "category": "Sensitive / Context-Specific",
        "description": "Race / ethnicity when labeled.",
        "mask": "[REDACTED]",
        "detectable": True,
        "default_enabled": False,
    },
    {
        "id": "SEXUAL_ORIENTATION",
        "name": "Sexual orientation",
        "category": "Sensitive / Context-Specific",
        "description": "Sexual orientation when labeled.",
        "mask": "[REDACTED]",
        "detectable": True,
        "default_enabled": False,
    },
    {
        "id": "RELIGIOUS_POLITICAL",
        "name": "Religious or political affiliation",
        "category": "Sensitive / Context-Specific",
        "description": "Religion or political affiliation when labeled.",
        "mask": "[REDACTED]",
        "detectable": True,
        "default_enabled": False,
    },
    {
        "id": "MEDICAL_INFO",
        "name": "Medical / health information",
        "category": "Sensitive / Context-Specific",
        "description": "Medical records or health details (PHI, labeled).",
        "mask": "[HEALTH]",
        "detectable": True,
        "default_enabled": False,
    },
    {
        "id": "EMPLOYMENT",
        "name": "Employment details",
        "category": "Sensitive / Context-Specific",
        "description": "Employer, job title, work history (labeled).",
        "mask": "[EMPLOYMENT]",
        "detectable": True,
        "default_enabled": False,
    },
    {
        "id": "EDUCATION",
        "name": "Education records",
        "category": "Sensitive / Context-Specific",
        "description": "Student IDs, transcripts, school records (labeled).",
        "mask": "[EDUCATION]",
        "detectable": True,
        "default_enabled": False,
    },
    # --- Online / digital ---
    {
        "id": "IP_ADDRESS",
        "name": "IP address",
        "category": "Online / Digital Identifiers",
        "description": "IPv4 addresses that may identify a person.",
        "mask": "***.***.***.***",
        "detectable": True,
        "default_enabled": False,
    },
    {
        "id": "MAC_ADDRESS",
        "name": "MAC address",
        "category": "Online / Digital Identifiers",
        "description": "Device hardware addresses.",
        "mask": "**:**:**:**:**:**",
        "detectable": True,
        "default_enabled": False,
    },
    {
        "id": "GEOLOCATION",
        "name": "Geolocation",
        "category": "Online / Digital Identifiers",
        "description": "Coordinates precise enough to locate a person.",
        "mask": "[GEO]",
        "detectable": True,
        "default_enabled": False,
    },
    {
        "id": "DEVICE_COOKIE_ID",
        "name": "Cookies / device IDs",
        "category": "Online / Digital Identifiers",
        "description": "Cookie or device identifiers tied to a person (labeled).",
        "mask": "[DEVICE_ID]",
        "detectable": True,
        "default_enabled": False,
    },
    {
        "id": "SOCIAL_HANDLE",
        "name": "Social media handle",
        "category": "Online / Digital Identifiers",
        "description": "Social profiles and @handles.",
        "mask": "[HANDLE]",
        "detectable": True,
        "default_enabled": False,
    },
    {
        "id": "PHOTO_VIDEO_ID",
        "name": "Identifiable photo / video",
        "category": "Online / Digital Identifiers",
        "description": "References to identifiable imagery IDs (not binary media).",
        "mask": "[MEDIA]",
        "detectable": True,
        "default_enabled": False,
    },
    # --- Derived / indirect ---
    {
        "id": "LOGIN_CREDENTIALS",
        "name": "Login credentials",
        "category": "Derived / Indirect PII",
        "description": "Passwords, PINs, security answers (labeled).",
        "mask": "[CREDENTIAL]",
        "detectable": True,
        "default_enabled": False,
    },
    {
        "id": "PURCHASE_HISTORY",
        "name": "Purchase history",
        "category": "Derived / Indirect PII",
        "description": "Order / invoice / transaction IDs (labeled).",
        "mask": "[PURCHASE]",
        "detectable": True,
        "default_enabled": False,
    },
    {
        "id": "MEMBERSHIP_ID",
        "name": "Membership / account numbers",
        "category": "Derived / Indirect PII",
        "description": "Loyalty, gym, or membership account numbers (labeled).",
        "mask": "********",
        "detectable": True,
        "default_enabled": False,
    },
    {
        "id": "BADGE_ID",
        "name": "Workplace badge / ID",
        "category": "Derived / Indirect PII",
        "description": "Employee badge or building access IDs (labeled).",
        "mask": "********",
        "detectable": True,
        "default_enabled": False,
    },
    {
        "id": "FACIAL_RECOGNITION_DATA",
        "name": "Facial recognition data",
        "category": "Derived / Indirect PII",
        "description": "Facial templates derived from images/video (text refs).",
        "mask": "[BIOMETRIC]",
        "detectable": True,
        "default_enabled": False,
    },
]

CATALOG_BY_ID: dict[str, PiiDetectionDef] = {d["id"]: d for d in PII_CATALOG}

DETECTABLE_IDS: frozenset[str] = frozenset(d["id"] for d in PII_CATALOG if d["detectable"])


def normalize_entity_id(raw: str) -> str | None:
    key = (raw or "").strip().upper()
    if not key:
        return None
    return ENTITY_ALIASES.get(key, key if key in CATALOG_BY_ID else None)


def default_detections_map() -> dict[str, dict[str, bool]]:
    return {d["id"]: {"enabled": d["default_enabled"]} for d in PII_CATALOG}


def default_policy_rules() -> dict[str, Any]:
    """Seed shape for new orgs — governance + per-detection toggles."""
    return {
        "models": {"allowed": []},
        "topics": {"blocked": []},
        "providers": {"blocked": []},
        "threats": {"action": "block", "threshold": 0.8},
        "pii": {
            "action": "mask",
            "detections": default_detections_map(),
        },
    }


def merge_detections_from_rules(rules: dict[str, Any] | None) -> dict[str, dict[str, bool]]:
    """Resolve org detections from policy rules (legacy list + new map)."""
    out = default_detections_map()
    if not isinstance(rules, dict):
        return out
    pii = rules.get("pii")
    if not isinstance(pii, dict):
        return out

    detections = pii.get("detections")
    if isinstance(detections, dict):
        for raw_id, cfg in detections.items():
            eid = normalize_entity_id(str(raw_id))
            if not eid or eid not in out:
                continue
            if isinstance(cfg, dict):
                out[eid] = {"enabled": bool(cfg.get("enabled", False))}
            elif isinstance(cfg, bool):
                out[eid] = {"enabled": cfg}
        return out

    # Legacy: pii.entities = ["EMAIL", "SSN", ...]
    entities = pii.get("entities")
    if isinstance(entities, list):
        enabled: set[str] = set()
        for item in entities:
            eid = normalize_entity_id(str(item))
            if eid:
                enabled.add(eid)
        for eid in out:
            out[eid] = {"enabled": eid in enabled}
    return out


def enabled_detectable_entities(detections: dict[str, dict[str, bool]]) -> list[str]:
    return sorted(
        eid
        for eid, cfg in detections.items()
        if cfg.get("enabled") and eid in DETECTABLE_IDS
    )
