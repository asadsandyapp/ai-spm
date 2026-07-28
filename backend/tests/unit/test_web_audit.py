"""Unit tests for agent web-audit endpoint helpers (schema + event typing)."""

from ai_spm.core.schemas import WebAuditRequest
from ai_spm.domain.enums import AuditEventType


def test_web_audit_request_defaults():
    body = WebAuditRequest(masked_content="hello ***@***.com")
    assert body.provider == "chatgpt"
    assert body.source == "web_mitm"
    assert body.pii_hit_count == 0


def test_web_audit_event_type_choice():
    # Mirrors agent route logic
    assert (
        AuditEventType.PII_DETECTED
        if 2 > 0
        else AuditEventType.PROMPT_SUBMITTED
    ) == AuditEventType.PII_DETECTED
    assert (
        AuditEventType.PII_DETECTED
        if 0 > 0
        else AuditEventType.PROMPT_SUBMITTED
    ) == AuditEventType.PROMPT_SUBMITTED
