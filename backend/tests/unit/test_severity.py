"""Unit tests for enterprise severity classification."""

from __future__ import annotations

from ai_spm.domain.enums import AuditEventType
from ai_spm.services.severity import (
    attach_severity,
    classify_event_severity,
    classify_pii_entities,
)


def test_critical_pii_is_high():
    assert classify_pii_entities(["US_SSN", "EMAIL_ADDRESS"], hit_count=2) == "high"
    assert classify_pii_entities(["CNIC", "TAX_ID"], hit_count=19) == "high"
    assert classify_pii_entities(["CREDIT_CARD"], hit_count=1) == "high"
    assert classify_pii_entities(["LOGIN_CREDENTIALS"], hit_count=1) == "high"


def test_medium_pii_defaults():
    assert classify_pii_entities(["EMAIL_ADDRESS"], hit_count=1) == "medium"
    assert classify_pii_entities(["PHONE_NUMBER", "PERSON_NAME"], hit_count=2) == "medium"


def test_low_pii_soft_attributes():
    assert classify_pii_entities(["GENDER"], hit_count=1) == "low"
    assert classify_pii_entities(["EMPLOYMENT", "EDUCATION"], hit_count=2) == "low"


def test_volume_escalates_medium_to_high():
    entities = ["EMAIL_ADDRESS"] * 16
    assert classify_pii_entities(entities, hit_count=16) == "high"


def test_threat_detected_is_high():
    assert (
        classify_event_severity(
            AuditEventType.THREAT_DETECTED,
            {"threat_severity": "high", "threat_type": "prompt_injection"},
        )
        == "high"
    )


def test_outbound_threat_can_be_medium():
    assert (
        classify_event_severity(
            AuditEventType.THREAT_DETECTED,
            {"threat_severity": "medium", "phase": "response"},
        )
        == "medium"
    )


def test_fail_closed_block_is_high():
    assert (
        classify_event_severity(
            AuditEventType.PROMPT_BLOCKED,
            {"fail_closed": True, "block_code": "SCANNER_ERROR"},
        )
        == "high"
    )


def test_policy_violation_is_medium():
    assert classify_event_severity(AuditEventType.POLICY_VIOLATION, {}) == "medium"


def test_pii_event_uses_entity_tiers():
    assert (
        classify_event_severity(
            AuditEventType.PII_DETECTED,
            {"pii_entities": ["EMAIL_ADDRESS"], "pii_hit_count": 1},
        )
        == "medium"
    )
    assert (
        classify_event_severity(
            AuditEventType.PII_DETECTED,
            {
                "pii_entities": ["CNIC", "US_SSN", "TAX_ID", "EMAIL_ADDRESS"],
                "pii_hit_count": 19,
            },
        )
        == "high"
    )
    assert (
        classify_event_severity(
            AuditEventType.PII_DETECTED,
            {"pii_entities": ["GENDER"], "pii_hit_count": 1},
        )
        == "low"
    )


def test_attach_severity_writes_metadata():
    meta = attach_severity(
        {"pii_entities": ["US_SSN"], "pii_hit_count": 1},
        AuditEventType.PII_DETECTED,
    )
    assert meta["severity"] == "high"
    assert "severity_factors" in meta
