"""Helpers for web-MITM audit payloads — keep human prompts, drop API JSON chunks."""

from __future__ import annotations

import json
from typing import Any


def _looks_like_prompt(text: str) -> bool:
    t = (text or "").strip()
    if len(t) < 2 or len(t) > 20_000:
        return False
    if t.startswith(("{", "[", "gAAAAA")):
        return False
    if t.lower() in {"user", "assistant", "system", "human", "model", "next", "text"}:
        return False
    if len(t) > 120 and " " not in t[:80] and "@" not in t:
        return False
    letters = sum(1 for c in t if c.isalpha())
    if letters < 2:
        return False
    if len(t) < 8 and "@" not in t and " " not in t:
        return False
    return True


def _from_messages(messages: list[Any]) -> str | None:
    last: str | None = None
    for msg in messages:
        if not isinstance(msg, dict):
            continue
        author = msg.get("author")
        role = author.get("role") if isinstance(author, dict) else msg.get("role")
        role = str(role or "user").lower()
        content = msg.get("content")
        texts: list[str] = []
        if isinstance(content, str):
            texts.append(content)
        elif isinstance(content, dict):
            parts = content.get("parts")
            if isinstance(parts, list):
                for part in parts:
                    if isinstance(part, str):
                        texts.append(part)
                    elif isinstance(part, dict) and isinstance(part.get("text"), str):
                        texts.append(part["text"])
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and isinstance(block.get("text"), str):
                    texts.append(block["text"])
                elif isinstance(block, str):
                    texts.append(block)
        for text in texts:
            if _looks_like_prompt(text) and role in ("user", "human", ""):
                last = text.strip()
    return last


def humanize_prompt_text(raw: str | None) -> str | None:
    """If ``raw`` is ChatGPT/Claude JSON, return the user message; else return cleaned text."""
    if not raw:
        return None
    text = raw.strip()
    if not text:
        return None
    if not text.startswith(("{", "[")):
        return text if _looks_like_prompt(text) or len(text) < 500 else text[:500]

    try:
        body = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return text[:2000]

    if isinstance(body, dict):
        for key in ("prompt", "input_text", "prompt_text", "query", "text"):
            val = body.get(key)
            if isinstance(val, str) and _looks_like_prompt(val):
                return val.strip()
        messages = body.get("messages")
        if isinstance(messages, list):
            found = _from_messages(messages)
            if found:
                return found
    return text[:2000]
