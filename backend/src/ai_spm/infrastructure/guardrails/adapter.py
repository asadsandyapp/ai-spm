"""Guardrails AI threat detection with pattern-based fallback."""

from __future__ import annotations

from dataclasses import dataclass

import structlog

logger = structlog.get_logger(__name__)

INJECTION_PATTERNS = [
    "ignore previous instructions",
    "ignore all previous",
    "disregard all prior",
    "disregard your instructions",
    "jailbreak",
    "dan mode",
    "do anything now",
    "you are now",
    "pretend you are",
    "bypass safety",
    "override your programming",
]

LEAKAGE_PATTERNS = [
    "system prompt",
    "internal instructions",
    "api key",
    "secret key",
    "password is",
]


@dataclass
class ThreatScanResult:
    is_threat: bool
    reason: str | None
    severity: str  # low, medium, high
    threat_type: str | None = None


class GuardrailsAdapter:
    """Scan prompts and responses for injection, jailbreak, and leakage."""

    def __init__(self) -> None:
        self._guard = None
        self._use_guardrails = False
        self._init_guardrails()

    def _init_guardrails(self) -> None:
        try:
            from guardrails import Guard
            from guardrails.hub import DetectPromptInjection, ToxicLanguage

            self._guard = Guard().use(
                DetectPromptInjection(on_fail="exception"),
                ToxicLanguage(threshold=0.8, on_fail="exception"),
            )
            self._use_guardrails = True
            logger.info("guardrails_engine_initialized")
        except Exception as exc:
            logger.warning("guardrails_unavailable_using_pattern_fallback", error=str(exc))
            self._use_guardrails = False

    def scan_inbound(self, text: str) -> ThreatScanResult:
        if not text.strip():
            return ThreatScanResult(is_threat=False, reason=None, severity="low")

        if self._use_guardrails and self._guard:
            try:
                self._guard.validate(text)
                return ThreatScanResult(is_threat=False, reason=None, severity="low")
            except Exception as exc:
                return ThreatScanResult(
                    is_threat=True,
                    reason=f"Guardrails threat detected: {exc}",
                    severity="high",
                    threat_type="prompt_injection",
                )

        return self._pattern_scan(text, inbound=True)

    def scan_outbound(self, text: str) -> ThreatScanResult:
        if not text.strip():
            return ThreatScanResult(is_threat=False, reason=None, severity="low")

        pii_leak = self._pattern_scan(text, inbound=False)
        if pii_leak.is_threat:
            return pii_leak

        if self._use_guardrails and self._guard:
            try:
                self._guard.validate(text)
            except Exception as exc:
                return ThreatScanResult(
                    is_threat=True,
                    reason=f"Response threat detected: {exc}",
                    severity="medium",
                    threat_type="response_leakage",
                )

        return ThreatScanResult(is_threat=False, reason=None, severity="low")

    def _pattern_scan(self, text: str, inbound: bool) -> ThreatScanResult:
        lower = text.lower()
        patterns = INJECTION_PATTERNS if inbound else LEAKAGE_PATTERNS
        threat_type = "prompt_injection" if inbound else "response_leakage"

        for pattern in patterns:
            if pattern in lower:
                label = "Prompt injection" if inbound else "Response leakage"
                return ThreatScanResult(
                    is_threat=True,
                    reason=f"{label} detected: '{pattern}'",
                    severity="high" if inbound else "medium",
                    threat_type=threat_type,
                )
        return ThreatScanResult(is_threat=False, reason=None, severity="low")
