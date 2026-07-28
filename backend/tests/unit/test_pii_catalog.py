"""Unit tests for enterprise PII detection catalog helpers."""

from ai_spm.services.pii_catalog import (
    default_policy_rules,
    enabled_detectable_entities,
    merge_detections_from_rules,
    normalize_entity_id,
)


def test_normalize_aliases():
    assert normalize_entity_id("email") == "EMAIL_ADDRESS"
    assert normalize_entity_id("SSN") == "US_SSN"
    assert normalize_entity_id("PHONE") == "PHONE_NUMBER"


def test_merge_legacy_entities_list():
    rules = {
        "pii": {
            "action": "mask",
            "entities": ["EMAIL", "SSN"],
        }
    }
    detections = merge_detections_from_rules(rules)
    assert detections["EMAIL_ADDRESS"]["enabled"] is True
    assert detections["US_SSN"]["enabled"] is True
    assert detections["PHONE_NUMBER"]["enabled"] is False


def test_default_policy_has_detections_map():
    rules = default_policy_rules()
    assert "detections" in rules["pii"]
    enabled = enabled_detectable_entities(rules["pii"]["detections"])
    assert "EMAIL_ADDRESS" in enabled
    assert "CREDIT_CARD" in enabled


def test_all_catalog_entities_are_detectable():
    from ai_spm.services.pii_catalog import DETECTABLE_IDS, PII_CATALOG

    assert len(DETECTABLE_IDS) == len(PII_CATALOG)
    assert all(d["detectable"] for d in PII_CATALOG)
