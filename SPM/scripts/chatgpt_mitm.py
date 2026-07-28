"""
MITM addon for mitmproxy — masks emails in ChatGPT web UI requests.

No browser extension. Requires:
  1. mitmproxy running as system/browser proxy
  2. mitmproxy CA certificate trusted by the OS/browser

Usage:
  mitmdump -s scripts/chatgpt_mitm.py --listen-port 8800
"""

from __future__ import annotations

import json
import re
from typing import Any

from mitmproxy import ctx, http

EMAIL_REDACTED = "[EMAIL_REDACTED]"

# Same pattern as src/masker.rs
EMAIL_REGEX = re.compile(
    r"(?i)\b[a-z0-9._%+-]+@[a-z0-9](?:[a-z0-9-]*[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)+\b"
)

# ChatGPT web UI API hosts (add more if your region uses different domains)
CHATGPT_HOSTS = (
    "chatgpt.com",
    "chat.openai.com",
    "api.openai.com",
)


def count_emails(text: str) -> int:
    return len(EMAIL_REGEX.findall(text))


def mask_emails(text: str) -> str:
    return EMAIL_REGEX.sub(EMAIL_REDACTED, text)


def mask_json_strings(value: Any) -> tuple[Any, int]:
    """Recursively mask emails in every JSON string value."""
    if isinstance(value, str):
        n = count_emails(value)
        return (mask_emails(value), n) if n else (value, 0)

    if isinstance(value, list):
        total = 0
        out = []
        for item in value:
            masked, n = mask_json_strings(item)
            out.append(masked)
            total += n
        return out, total

    if isinstance(value, dict):
        total = 0
        out = {}
        for key, item in value.items():
            masked, n = mask_json_strings(item)
            out[key] = masked
            total += n
        return out, total

    return value, 0


def is_chatgpt_request(flow: http.HTTPFlow) -> bool:
    if flow.request.method not in ("POST", "PUT", "PATCH"):
        return False

    host = flow.request.host.lower()
    return any(host == h or host.endswith("." + h) for h in CHATGPT_HOSTS)


class ChatGptEmailMasker:
    def request(self, flow: http.HTTPFlow) -> None:
        if not is_chatgpt_request(flow):
            return

        content_type = flow.request.headers.get("content-type", "")
        if "application/json" not in content_type.lower():
            return

        raw = flow.request.get_text(strict=False)
        if not raw:
            return

        try:
            body = json.loads(raw)
        except json.JSONDecodeError:
            return

        masked_body, email_count = mask_json_strings(body)
        if email_count == 0:
            return

        flow.request.set_text(json.dumps(masked_body, separators=(",", ":")))
        ctx.log.info(
            f"Masked {email_count} email(s) in {flow.request.method} {flow.request.pretty_url}"
        )


addons = [ChatGptEmailMasker()]
