"""Presidio PII detection and masking with regex fallback for dev/CI."""

from __future__ import annotations

import re
from dataclasses import dataclass

import structlog

logger = structlog.get_logger(__name__)

CONFIDENCE_THRESHOLD = 0.7

MASK_FORMATS = {
    "CNIC": "*************",
    "US_SSN": "***-**-****",
    "CREDIT_CARD": "****-****-****-1234",
    "EMAIL_ADDRESS": "***@***.com",
    "PHONE_NUMBER": "***-***-****",
}

REGEX_PATTERNS = {
    "CNIC": re.compile(r"\b\d{5}-\d{7}-\d\b"),
    "US_SSN": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    "CREDIT_CARD": re.compile(r"\b(?:\d{4}[\s-]?){3}\d{4}\b"),
    "EMAIL_ADDRESS": re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"),
    "PHONE_NUMBER": re.compile(r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"),
}


@dataclass
class PIIScanResult:
    masked_text: str
    entities: list[str]
    entity_count: int


class PresidioAdapter:
    """Detect and mask PII using Presidio when available, regex fallback otherwise."""

    def __init__(self) -> None:
        self._analyzer = None
        self._anonymizer = None
        self._use_presidio = False
        self._init_presidio()

    def _init_presidio(self) -> None:
        try:
            from presidio_analyzer import AnalyzerEngine, Pattern, PatternRecognizer
            from presidio_analyzer.nlp_engine import NlpEngineProvider
            from presidio_anonymizer import AnonymizerEngine

            provider = NlpEngineProvider(
                nlp_configuration={
                    "nlp_engine_name": "spacy",
                    "models": [{"lang_code": "en", "model_name": "en_core_web_sm"}],
                }
            )
            nlp_engine = provider.create_engine()
            analyzer = AnalyzerEngine(nlp_engine=nlp_engine, supported_languages=["en"])

            cnic_pattern = Pattern(name="cnic_pattern", regex=r"\d{5}-\d{7}-\d", score=0.9)
            cnic_recognizer = PatternRecognizer(
                supported_entity="CNIC",
                patterns=[cnic_pattern],
                supported_language="en",
            )
            analyzer.registry.add_recognizer(cnic_recognizer)

            self._analyzer = analyzer
            self._anonymizer = AnonymizerEngine()
            self._use_presidio = True
            logger.info("presidio_engine_initialized")
        except Exception as exc:
            logger.warning("presidio_unavailable_using_regex_fallback", error=str(exc))
            self._use_presidio = False

    def scan_and_mask(self, text: str) -> PIIScanResult:
        if not text:
            return PIIScanResult(masked_text="", entities=[], entity_count=0)

        if self._use_presidio and self._analyzer and self._anonymizer:
            return self._presidio_mask(text)
        return self._regex_mask(text)

    def _presidio_mask(self, text: str) -> PIIScanResult:
        from presidio_anonymizer.entities import OperatorConfig

        results = self._analyzer.analyze(
            text=text,
            language="en",
            entities=list(MASK_FORMATS.keys()),
            score_threshold=CONFIDENCE_THRESHOLD,
        )
        entities = sorted({r.entity_type for r in results})
        operators = {
            entity: OperatorConfig(
                "replace", {"new_value": MASK_FORMATS.get(entity, "[REDACTED]")}
            )
            for entity in entities
        }
        anonymized = self._anonymizer.anonymize(
            text=text,
            analyzer_results=results,
            operators=operators,
        )
        return PIIScanResult(
            masked_text=anonymized.text,
            entities=entities,
            entity_count=len(results),
        )

    def _regex_mask(self, text: str) -> PIIScanResult:
        masked = text
        entities: list[str] = []
        for entity, pattern in REGEX_PATTERNS.items():
            if pattern.search(masked):
                entities.append(entity if entity != "US_SSN" else "SSN")
                mask = MASK_FORMATS.get(entity, f"[{entity}_REDACTED]")
                masked = pattern.sub(mask, masked)
        return PIIScanResult(masked_text=masked, entities=entities, entity_count=len(entities))
