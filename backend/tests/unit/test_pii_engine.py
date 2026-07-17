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
