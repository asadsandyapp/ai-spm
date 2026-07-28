"""Presidio PII detection and masking with regex fallback for dev/CI."""

from __future__ import annotations

from dataclasses import dataclass

import structlog

from ai_spm.infrastructure.presidio.patterns import (
    ENTITY_AUDIT_LABEL,
    MASK_FORMATS,
    REGEX_PATTERNS,
    iter_patterns_for,
)

logger = structlog.get_logger(__name__)

CONFIDENCE_THRESHOLD = 0.7

# Presidio NLP entity types → our catalog IDs.
_PRESIDIO_NLP_MAP = {
    "PERSON_NAME": "PERSON",
    "STREET_ADDRESS": "LOCATION",
}

# Built-in Presidio pattern entities we prefer to run through the analyzer first.
_PRESIDIO_NATIVE = frozenset(
    {"CNIC", "US_SSN", "CREDIT_CARD", "EMAIL_ADDRESS", "PHONE_NUMBER"}
)


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

    def scan_and_mask(
        self,
        text: str,
        entities: list[str] | None = None,
    ) -> PIIScanResult:
        if not text:
            return PIIScanResult(masked_text="", entities=[], entity_count=0)

        active = self._resolve_entities(entities)
        if not active:
            return PIIScanResult(masked_text=text, entities=[], entity_count=0)

        if self._use_presidio and self._analyzer and self._anonymizer:
            return self._presidio_mask(text, active)
        return self._regex_mask(text, active)

    def _resolve_entities(self, entities: list[str] | None) -> list[str]:
        if entities is None:
            return list(REGEX_PATTERNS.keys())
        # Only known detectable patterns; empty list = mask nothing.
        return [e for e in entities if e in MASK_FORMATS]

    def _presidio_mask(self, text: str, entities: list[str]) -> PIIScanResult:
        from presidio_anonymizer.entities import OperatorConfig

        native = [e for e in entities if e in _PRESIDIO_NATIVE]
        nlp_wanted = [e for e in entities if e in _PRESIDIO_NLP_MAP]
        custom = [e for e in entities if e not in native and e not in nlp_wanted]

        analyze_entities = list(native) + [_PRESIDIO_NLP_MAP[e] for e in nlp_wanted]
        results = []
        if analyze_entities:
            results = self._analyzer.analyze(
                text=text,
                language="en",
                entities=analyze_entities,
                score_threshold=CONFIDENCE_THRESHOLD,
            )

        # Map Presidio NLP types back to catalog IDs for masking / audit.
        reverse_nlp = {v: k for k, v in _PRESIDIO_NLP_MAP.items()}
        remapped = []
        for r in results:
            catalog_id = reverse_nlp.get(r.entity_type, r.entity_type)
            if catalog_id not in entities and r.entity_type not in entities:
                continue
            r.entity_type = catalog_id if catalog_id in MASK_FORMATS else r.entity_type
            remapped.append(r)
        results = remapped

        found = sorted({r.entity_type for r in results})
        operators = {
            entity: OperatorConfig(
                "replace", {"new_value": MASK_FORMATS.get(entity, "[REDACTED]")}
            )
            for entity in found
        }
        masked = text
        if results and operators:
            anonymized = self._anonymizer.anonymize(
                text=text,
                analyzer_results=results,
                operators=operators,
            )
            masked = anonymized.text

        # Regex for catalog entities Presidio didn't cover (and NLP misses).
        regex_entities = custom + [e for e in native + nlp_wanted if e not in found]
        if regex_entities:
            regex_result = self._regex_mask(masked, regex_entities)
            audit = sorted(set(found) | set(regex_result.entities))
            return PIIScanResult(
                masked_text=regex_result.masked_text,
                entities=[ENTITY_AUDIT_LABEL.get(e, e) for e in audit],
                entity_count=len(results) + regex_result.entity_count,
            )

        return PIIScanResult(
            masked_text=masked,
            entities=[ENTITY_AUDIT_LABEL.get(e, e) for e in found],
            entity_count=len(results),
        )

    def _regex_mask(self, text: str, entities: list[str]) -> PIIScanResult:
        masked = text
        found: list[str] = []
        count = 0
        for entity, pattern, mask in iter_patterns_for(entities):
            masked, n = pattern.subn(mask, masked)
            if not n:
                continue
            count += n
            found.append(ENTITY_AUDIT_LABEL.get(entity, entity))
        return PIIScanResult(masked_text=masked, entities=found, entity_count=count)
