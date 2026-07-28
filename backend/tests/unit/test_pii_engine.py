"""PII engine unit tests."""

from ai_spm.infrastructure.presidio.adapter import PresidioAdapter


def test_masks_cnic():
    engine = PresidioAdapter()
    result = engine.scan_and_mask("My CNIC is 35202-1234567-9")
    assert "35202-1234567-9" not in result.masked_text
    assert "CNIC" in result.entities or len(result.entities) > 0


def test_masks_ssn():
    engine = PresidioAdapter()
    result = engine.scan_and_mask("SSN: 123-45-6789")
    assert "123-45-6789" not in result.masked_text


def test_masks_credit_card():
    engine = PresidioAdapter()
    result = engine.scan_and_mask("Card 4111 1111 1111 1111")
    assert "4111 1111 1111 1111" not in result.masked_text


def test_no_pii_unchanged():
    engine = PresidioAdapter()
    text = "Summarize this quarterly report for the team."
    result = engine.scan_and_mask(text)
    assert result.masked_text == text
    assert result.entities == []


def test_respects_enabled_entities_only_email():
    engine = PresidioAdapter()
    text = "email a@b.com and phone 555-123-4567"
    result = engine.scan_and_mask(text, entities=["EMAIL_ADDRESS"])
    assert "***@***.com" in result.masked_text
    assert "555-123-4567" in result.masked_text


def test_masks_catalog_labeled_entities():
    engine = PresidioAdapter()
    text = (
        "My name is Alice Smith. Gender: female. Password: hunter2. "
        "Employee ID: E-99881. MAC 00:1A:2B:3C:4D:5E"
    )
    result = engine.scan_and_mask(
        text,
        entities=[
            "PERSON_NAME",
            "GENDER",
            "LOGIN_CREDENTIALS",
            "BADGE_ID",
            "MAC_ADDRESS",
        ],
    )
    assert "Alice Smith" not in result.masked_text
    assert "Gender: female" not in result.masked_text
    assert "hunter2" not in result.masked_text
    assert "E-99881" not in result.masked_text
    assert "00:1A:2B:3C:4D:5E" not in result.masked_text


def test_catalog_off_leaves_labeled_pii():
    engine = PresidioAdapter()
    text = "Password: hunter2 and Tax ID: 12-3456789"
    result = engine.scan_and_mask(text, entities=["EMAIL_ADDRESS"])
    assert "hunter2" in result.masked_text
    assert "12-3456789" in result.masked_text
