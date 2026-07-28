"""
AI-SPM web UI mitmproxy addon — fast, policy-aware PII masking.

Critical: ChatGPT/Claude answers are SSE/chunked streams. Buffering them in
mitmproxy causes "Connection interrupted" mid-answer. We force response
streaming for conversation paths and never rewrite those response bodies.

Policy file: /etc/ai-spm/pii-policy.json (agent heartbeat).
Patterns: pii_rules.py (parity with gateway patterns.py).
"""

from __future__ import annotations

import json
import re
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import unquote

from mitmproxy import ctx, http

from pii_rules import ENTITY_APPLY_ORDER, MASK_FORMATS, REGEX_PATTERNS, iter_patterns_for

PII_POLICY_PATH = Path("/etc/ai-spm/pii-policy.json")
WEB_AUDIT_URL = "http://127.0.0.1:8092/web-audit"
DEFAULT_ENABLED = frozenset(
    {"EMAIL_ADDRESS", "PHONE_NUMBER", "US_SSN", "CNIC", "CREDIT_CARD"}
)

MAX_SCAN_BYTES = 256_000
AISPM_HOOK_PATH = "/aispm-web-mask.js"

# Paths that may carry user prompts (logged-in + guest/unauth ChatGPT web).
_SCAN_PATH_HINTS = (
    "/backend-api/f/conversation",
    "/backend-api/conversation",
    "/backend-anon/f/conversation",
    "/backend-anon/conversation",
    "/unauth-mweb/conversation",
    "prompt-autocompletions",
    "/chat_conversations/",
    "/append_message",
    "/v1/messages",
    "/v1/chat/completions",
    "/completion",
    "/streamGenerate",
    "/StreamGenerate",
    "/f/req",
)

# Never scan / rewrite these — metadata, telemetry, or stream control.
_NOISE_PATH_HINTS = (
    "/events/",
    "/sentinel/",
    "/lat/",
    "/telemetry",
    "/statsc/",
    "/runtime",
    "/page-view",
    "/performance",
    "/csrf",
    "/accounts/",
    "/ces/",
)

_AUDIT_PATH_HINTS = (
    "/backend-api/f/conversation",
    "/backend-api/conversation",
    "/backend-anon/f/conversation",
    "/backend-anon/conversation",
    "/unauth-mweb/conversation",
    "prompt-autocompletions",
    "/chat_conversations/",
    "/completion",
    "/append_message",
    "/v1/messages",
    "/v1beta/",
    "/streamGenerate",
    "/StreamGenerate",
)

# Response paths that must stream (never buffer full answer).
_STREAM_PATH_HINTS = (
    "/conversation",
    "/completion",
    "/backend-api/",
    "/backend-anon/",
    "/unauth-mweb/",
    "streamgenerate",
    "/append_message",
    "/v1/messages",
    "/v1/chat/completions",
)

PII_RULES: list[tuple[str, re.Pattern[str], str]] = [
    (eid, REGEX_PATTERNS[eid], MASK_FORMATS[eid])
    for eid in ENTITY_APPLY_ORDER
    if eid in REGEX_PATTERNS
]

_LABEL_HINT = re.compile(
    r"(?i)\b(?:password|passwd|pwd|passcode|pin|otp|gender|sex|ethnicity|race|"
    r"maiden|username|user\s*name|handle|employee\s*id|badge|diagnosis|"
    r"born\s+in|place\s+of\s+birth|marital|religion|orientation|fingerprint|"
    r"biometric|license\s*plate|member\s*id|order\s*id|invoice|transaction|"
    r"device\s*id|cookie\s*id|my\s+name\s+is|full\s*name|street|avenue|road|"
    r"employer|works?\s+at|student\s*id|mac\s*address|iban|passport|"
    r"driver'?s?\s*license|tax\s*id|ein)\b"
    r"|@"
)

# Skip metadata strings that look like IDs / ciphertext (never rewrite).
_META_STRING = re.compile(
    r"^(?:"
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"  # UUID
    r"|gAAAAA[A-Za-z0-9+/=_-]{20,}"  # ChatGPT ciphertext
    r"|[A-Za-z0-9_-]{40,}"  # long tokens
    r"|r_[a-z0-9]+"  # request ids
    r")$",
    re.IGNORECASE,
)

WEB_UI_HOSTS = (
    "chatgpt.com",
    "chat.openai.com",
    "claude.ai",
    "gemini.google.com",
    "openai.com",
)

_policy_cache: tuple[float, frozenset[str]] | None = None
_rules_cache: tuple[frozenset[str], list[tuple[str, re.Pattern[str], str]]] | None = None
_POLICY_TTL_SEC = 30.0


def load_enabled_entities() -> frozenset[str]:
    global _policy_cache
    now = time.monotonic()
    if _policy_cache and (now - _policy_cache[0]) < _POLICY_TTL_SEC:
        return _policy_cache[1]

    enabled = DEFAULT_ENABLED
    try:
        if PII_POLICY_PATH.is_file():
            data = json.loads(PII_POLICY_PATH.read_text(encoding="utf-8"))
            raw = data.get("enabled_entities")
            if isinstance(raw, list):
                enabled = frozenset(str(x).upper() for x in raw)
    except Exception as exc:
        ctx.log.warn(f"[AI-SPM] Failed to read {PII_POLICY_PATH}: {exc}")

    _policy_cache = (now, enabled)
    return enabled


def active_rules(enabled: frozenset[str]) -> list[tuple[str, re.Pattern[str], str]]:
    global _rules_cache
    if _rules_cache and _rules_cache[0] == enabled:
        return _rules_cache[1]
    rules = list(iter_patterns_for(list(enabled)))
    _rules_cache = (enabled, rules)
    return rules


def should_scan_path(path: str) -> bool:
    p = (path or "").lower()
    if any(n in p for n in _NOISE_PATH_HINTS):
        return False
    return any(h.lower() in p for h in _SCAN_PATH_HINTS)


def should_audit_path(path: str) -> bool:
    p = (path or "").lower()
    if any(n in p for n in _NOISE_PATH_HINTS):
        return False
    return any(h.lower() in p for h in _AUDIT_PATH_HINTS)


def should_stream_response(flow: http.HTTPFlow) -> bool:
    """True when buffering the body would break live AI answers."""
    if not flow.response:
        return False
    ct = flow.response.headers.get("content-type", "").lower()
    if (
        "text/event-stream" in ct
        or "application/grpc" in ct
        or "application/octet-stream" in ct
        or "stream" in ct
    ):
        return True
    # ChatGPT/Claude/Gemini answers are POST streams — never buffer them.
    if flow.request.method in ("POST", "PUT", "PATCH"):
        path = (flow.request.path or "").lower()
        if any(h in path for h in _STREAM_PATH_HINTS):
            return True
    return False


def normalize_escaped_pii(text: str) -> str:
    """Decode common @ encodings Chrome/guest payloads use so email regex can match."""
    if not text:
        return text
    # Collapse any run of backslashes before u0040 / x40 (wire or double-escaped).
    out = re.sub(r"\\+u0040", "@", text, flags=re.IGNORECASE)
    out = re.sub(r"\\+x40", "@", out, flags=re.IGNORECASE)
    out = (
        out.replace("%40", "@")
        .replace("&#64;", "@")
        .replace("&#x40;", "@")
        .replace("&commat;", "@")
    )
    return out


def looks_like_pii(text: str) -> bool:
    """Cheap pre-filter — do NOT treat bare digits alone as PII (UUIDs break streams)."""
    if not text:
        return False
    if "@" in text or "@" in normalize_escaped_pii(text):
        return True
    return _LABEL_HINT.search(text) is not None


def looks_like_user_prompt(text: str) -> bool:
    """Reject encrypted blobs / RPC tokens — keep human chat text only."""
    t = (text or "").strip()
    if len(t) < 2 or len(t) > 20_000:
        return False
    if t.startswith(("{", "[", "gAAAAA", "http://", "https://")):
        return False
    if _META_STRING.match(t):
        return False
    if t.lower() in {"user", "assistant", "system", "human", "model", "next", "text", "message"}:
        return False
    if len(t) > 120 and " " not in t[:80] and "@" not in t:
        return False
    letters = sum(1 for c in t if c.isalpha())
    if letters < 2:
        return False
    return bool(re.search(r"\s", t) or "@" in t)


def provider_from_host(host: str) -> str:
    h = (host or "").lower()
    if "claude" in h or "anthropic" in h:
        return "anthropic"
    if "gemini" in h or "google" in h:
        return "google"
    return "chatgpt"


def _collect_prompt_strings(value: Any, out: list[str]) -> None:
    if isinstance(value, str):
        if looks_like_user_prompt(value):
            out.append(value)
        return
    if isinstance(value, list):
        for item in value:
            _collect_prompt_strings(item, out)
        return
    if isinstance(value, dict):
        role = None
        if isinstance(value.get("author"), dict):
            role = value["author"].get("role")
        role = role or value.get("role")
        if role is not None and str(role).lower() not in {"user", "human"}:
            return
        for key in (
            "parts",
            "content",
            "messages",
            "input",
            "prompt",
            "text",
            "query",
            "value",
            "ops",
            "patch",
        ):
            if key in value:
                _collect_prompt_strings(value[key], out)
        for key, item in value.items():
            if key in {
                "author",
                "role",
                "id",
                "metadata",
                "model",
                "action",
                "parent_message_id",
            }:
                continue
            if isinstance(item, (dict, list)):
                _collect_prompt_strings(item, out)


def extract_user_prompt(raw: str, host: str) -> str | None:
    if not raw:
        return None
    host_l = (host or "").lower()
    try:
        body = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        body = None

    if body is not None:
        candidates: list[str] = []
        _collect_prompt_strings(body, candidates)
        if candidates:
            return max(candidates, key=len)

    if host_l.endswith(("chatgpt.com", "openai.com")) and "f.req=" in raw:
        try:
            frag = raw.split("f.req=", 1)[1].split("&", 1)[0]
            decoded = unquote(frag)
            inner = json.loads(decoded)
            if isinstance(inner, list) and len(inner) > 1:
                payload = inner[1]
                if isinstance(payload, str):
                    payload = json.loads(payload)
                if isinstance(payload, list):
                    for row in payload:
                        if (
                            isinstance(row, list)
                            and len(row) >= 1
                            and isinstance(row[0], str)
                            and looks_like_user_prompt(row[0])
                        ):
                            return row[0]
        except Exception:
            pass

    if looks_like_user_prompt(raw):
        return raw.strip()
    return None


def mask_pii(
    text: str, enabled: frozenset[str] | None = None
) -> tuple[str, int, list[str]]:
    if not text or not looks_like_pii(text):
        return text, 0, []
    if enabled is None:
        enabled = load_enabled_entities()
    if not enabled:
        return text, 0, []
    masked = text
    hits = 0
    entities: list[str] = []
    for name, pattern, replacement in active_rules(enabled):
        masked, n = pattern.subn(replacement, masked)
        if n:
            hits += n
            entities.append(name)
    return masked, hits, entities


def mask_json_strings(
    value: Any, enabled: frozenset[str] | None = None
) -> tuple[Any, int, list[str]]:
    """Mask only human prompt strings — never UUIDs / tokens / metadata."""
    if enabled is None:
        enabled = load_enabled_entities()
    if isinstance(value, str):
        if _META_STRING.match(value.strip()) or not looks_like_user_prompt(value):
            return value, 0, []
        if not looks_like_pii(value):
            return value, 0, []
        masked, n, ents = mask_pii(value, enabled)
        return (masked, n, ents) if n else (value, 0, [])
    if isinstance(value, list):
        total = 0
        all_ents: list[str] = []
        out = []
        for item in value:
            masked, n, ents = mask_json_strings(item, enabled)
            out.append(masked)
            total += n
            all_ents.extend(ents)
        return out, total, all_ents
    if isinstance(value, dict):
        total = 0
        all_ents: list[str] = []
        out = {}
        for key, item in value.items():
            # Never rewrite id / auth / model metadata fields.
            if key in {
                "id",
                "parent_message_id",
                "conversation_id",
                "model",
                "authorization",
                "token",
                "access_token",
                "device_id",
                "oai-device-id",
            }:
                out[key] = item
                continue
            masked, n, ents = mask_json_strings(item, enabled)
            out[key] = masked
            total += n
            all_ents.extend(ents)
        return out, total, all_ents
    return value, 0, []


def is_web_ui_host(host: str) -> bool:
    host = (host or "").lower()
    return any(host == h or host.endswith("." + h) for h in WEB_UI_HOSTS)


def mask_raw_body(
    raw: str, enabled: frozenset[str] | None = None
) -> tuple[str, int, list[str]]:
    if not raw:
        return raw, 0, []
    if enabled is None:
        enabled = load_enabled_entities()
    # Prefer native JSON parse first — json.loads already turns \u0040 into @.
    try:
        body = json.loads(raw)
        masked, n, ents = mask_json_strings(body, enabled)
        if n:
            return json.dumps(masked, separators=(",", ":"), ensure_ascii=False), n, ents
    except (json.JSONDecodeError, TypeError):
        pass
    wire = normalize_escaped_pii(raw)
    if wire != raw:
        try:
            body = json.loads(wire)
            masked, n, ents = mask_json_strings(body, enabled)
            if n:
                return json.dumps(masked, separators=(",", ":"), ensure_ascii=False), n, ents
        except (json.JSONDecodeError, TypeError):
            pass
    # Only mask non-JSON when it looks like a human prompt with PII.
    if looks_like_user_prompt(raw) and looks_like_pii(raw):
        return mask_pii(raw, enabled)
    if wire != raw and looks_like_user_prompt(wire) and looks_like_pii(wire):
        return mask_pii(wire, enabled)
    return raw, 0, []


def _post_web_audit(payload: dict[str, Any]) -> None:
    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            WEB_AUDIT_URL,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=2) as resp:
            resp.read()
    except Exception as exc:
        ctx.log.warn(f"[AI-SPM] web-audit failed (fail-open): {exc}")


def report_web_audit(
    *,
    provider: str,
    masked_prompt: str,
    original_prompt: str | None = None,
    entities: list[str] | None = None,
    hit_count: int = 0,
) -> None:
    if not masked_prompt:
        return
    payload = {
        "provider": provider,
        "model": "web-ui",
        "masked_content": masked_prompt[:8000],
        "original_content": (original_prompt[:8000] if original_prompt else None),
        "pii_entities": entities or [],
        "pii_hit_count": hit_count,
        "source": "web_mitm",
    }
    threading.Thread(target=_post_web_audit, args=(payload,), daemon=True).start()


def _pattern_to_js(pattern: re.Pattern[str], red: str) -> str:
    flags = "g"
    if pattern.flags & re.IGNORECASE:
        flags += "i"
    return (
        f'{{ re: new RegExp({json.dumps(pattern.pattern)}, {json.dumps(flags)}), '
        f"red: {json.dumps(red)} }}"
    )


def build_ui_redact_script_body(enabled: frozenset[str]) -> str:
    """JavaScript body for guest/incognito composer masking (ProseMirror + encrypt path)."""
    parts = [
        _pattern_to_js(pattern, red)
        for eid, pattern, red in PII_RULES
        if eid in enabled
    ]
    rules_js = ",\n    ".join(parts) if parts else ""
    return f"""(function () {{
  if (window.__AISPM_UI_MASK__) return;
  window.__AISPM_UI_MASK__ = true;
  var RULES = [{rules_js}];
  var IS_FIREFOX = /Firefox/i.test(navigator.userAgent);
  var IS_CHROME = !IS_FIREFOX && /Chrome|Chromium|Edg\\//i.test(navigator.userAgent);

  // Chrome guest: Trusted Types can block inline hooks — allow our script early.
  try {{
    if (window.trustedTypes && trustedTypes.createPolicy && !window.__AISPM_TT__) {{
      window.__AISPM_TT__ = trustedTypes.createPolicy("aispm-web-mask", {{
        createHTML: function (s) {{ return s; }},
        createScript: function (s) {{ return s; }},
        createScriptURL: function (s) {{ return s; }}
      }});
    }}
  }} catch (e) {{}}

  // Prevent Service Workers from serving unhooked HTML (Chrome incognito guest).
  try {{
    if (navigator.serviceWorker) {{
      navigator.serviceWorker.register = function () {{
        return Promise.reject(new Error("AI-SPM: service worker blocked"));
      }};
      if (navigator.serviceWorker.getRegistrations) {{
        navigator.serviceWorker.getRegistrations().then(function (regs) {{
          for (var i = 0; i < regs.length; i++) {{
            try {{ regs[i].unregister(); }} catch (e2) {{}}
          }}
        }});
      }}
    }}
  }} catch (e) {{}}

  function maskText(s) {{
    var out = String(s);
    for (var i = 0; i < RULES.length; i++) {{
      RULES[i].re.lastIndex = 0;
      out = out.replace(RULES[i].re, RULES[i].red);
    }}
    return out;
  }}

  function alreadyMasked(s) {{
    return /\\*\\*\\*@\\*\\*\\*|\\[EMAIL|REDACTED/i.test(s);
  }}

  function isProtocolBlob(s) {{
    if (!s || typeof s !== "string") return true;
    var t = s.trim();
    if (t.indexOf("gAAAAA") === 0) return true;
    if (t.length > 800 && (t.charAt(0) === "{{" || t.charAt(0) === "[")) return true;
    return false;
  }}

  function decodeAtEscapes(s) {{
    if (!s || typeof s !== "string") return s;
    return s
      .replace(/\\\\u0040/gi, "@")
      .replace(/\\\\x40/gi, "@")
      .replace(/%40/g, "@")
      .replace(/&#64;/g, "@")
      .replace(/&#x40;/gi, "@");
  }}

  function maskStringIfPii(s) {{
    if (!s || typeof s !== "string" || alreadyMasked(s) || isProtocolBlob(s)) return s;
    var decoded = decodeAtEscapes(s);
    var out = maskText(decoded);
    return out === decoded ? s : out;
  }}

  function shouldMaskString(s) {{
    if (!s || typeof s !== "string" || alreadyMasked(s) || isProtocolBlob(s)) return false;
    if (s.length < 3 || s.length > 50000) return false;
    var decoded = decodeAtEscapes(s);
    for (var i = 0; i < RULES.length; i++) {{
      RULES[i].re.lastIndex = 0;
      if (RULES[i].re.test(decoded)) return true;
    }}
    return false;
  }}

  function looksLikePii(s) {{
    return shouldMaskString(s);
  }}

  // Guest encrypt: mask PII in strings at encode/stringify time — never deep-clone objects.
  // Chrome: use defineProperty so later page scripts cannot overwrite our hooks.
  (function installEncryptionHooks() {{
    function aispmReplacer(key, value) {{
      return typeof value === "string" ? maskStringIfPii(value) : value;
    }}
    function wrapStringify(origStringify) {{
      return function (value, replacer, space) {{
        if (typeof replacer === "function") {{
          var userReplacer = replacer;
          replacer = function (key, val) {{
            var out = userReplacer.call(this, key, val);
            return typeof out === "string" ? maskStringIfPii(out) : out;
          }};
        }} else if (Array.isArray(replacer)) {{
          var allowed = replacer;
          replacer = function (key, val) {{
            if (allowed.length && key !== "" && allowed.indexOf(key) < 0) return undefined;
            return typeof val === "string" ? maskStringIfPii(val) : val;
          }};
        }} else {{
          replacer = aispmReplacer;
        }}
        return origStringify.call(this, value, replacer, space);
      }};
    }}
    try {{
      var origStringify = JSON.stringify;
      var wrapped = wrapStringify(origStringify);
      try {{
        Object.defineProperty(JSON, "stringify", {{
          configurable: true,
          enumerable: false,
          writable: true,
          value: wrapped
        }});
      }} catch (eDef) {{
        JSON.stringify = wrapped;
      }}
    }} catch (e) {{}}

    try {{
      var origEncode = TextEncoder.prototype.encode;
      var wrappedEncode = function (input) {{
        if (typeof input === "string") input = maskStringIfPii(input);
        return origEncode.call(this, input);
      }};
      try {{
        Object.defineProperty(TextEncoder.prototype, "encode", {{
          configurable: true,
          enumerable: false,
          writable: true,
          value: wrappedEncode
        }});
      }} catch (eDef2) {{
        TextEncoder.prototype.encode = wrappedEncode;
      }}
    }} catch (e) {{}}

    try {{
      if (window.crypto && crypto.subtle && crypto.subtle.encrypt) {{
        var origEncrypt = crypto.subtle.encrypt.bind(crypto.subtle);
        crypto.subtle.encrypt = function (algorithm, key, plain) {{
          try {{
            if (plain instanceof ArrayBuffer || ArrayBuffer.isView(plain)) {{
              var bytes = plain instanceof ArrayBuffer
                ? new Uint8Array(plain)
                : new Uint8Array(plain.buffer, plain.byteOffset, plain.byteLength);
              if (bytes.length > 0 && bytes.length < 50000) {{
                var text = new TextDecoder().decode(bytes);
                var masked = maskStringIfPii(text);
                if (masked !== text) plain = new TextEncoder().encode(masked);
              }}
            }}
          }} catch (e) {{}}
          return origEncrypt(algorithm, key, plain);
        }};
      }}
    }} catch (e) {{}}

    // Chrome guest: btoa often wraps prompt bytes before encrypt — mask there too.
    if (IS_CHROME) {{
      try {{
        var origBtoa = window.btoa.bind(window);
        window.btoa = function (s) {{
          if (typeof s === "string") s = maskStringIfPii(s);
          return origBtoa(s);
        }};
      }} catch (e) {{}}
    }}
  }})();

  function getComposerEl() {{
    return document.getElementById("prompt-textarea")
      || document.querySelector('[data-testid="composer"] [contenteditable="true"]')
      || document.querySelector("div.ProseMirror")
      || document.querySelector("textarea#prompt-textarea")
      || document.querySelector("textarea[data-id]")
      || document.querySelector("form textarea");
  }}

  function getComposerText(el) {{
    if (!el) return "";
    var tag = (el.tagName || "").toUpperCase();
    if (tag === "TEXTAREA" || tag === "INPUT") return el.value || "";
    return el.innerText || el.textContent || "";
  }}

  function setNativeValue(el, value) {{
    try {{
      var proto = Object.getPrototypeOf(el);
      var desc = Object.getOwnPropertyDescriptor(proto, "value");
      if (desc && desc.set) desc.set.call(el, value);
      else el.value = value;
    }} catch (e) {{
      el.value = value;
    }}
    try {{ el.dispatchEvent(new Event("input", {{ bubbles: true }})); }} catch (e2) {{}}
    try {{ el.dispatchEvent(new Event("change", {{ bubbles: true }})); }} catch (e3) {{}}
  }}

  function notifyComposerInput(el) {{
    if (!el) return;
    try {{
      el.dispatchEvent(new InputEvent("input", {{ bubbles: true, inputType: "insertReplacementText" }}));
    }} catch (e) {{
      try {{ el.dispatchEvent(new Event("input", {{ bubbles: true }})); }} catch (e2) {{}}
    }}
  }}

  // Primary path: mutate ProseMirror text nodes directly (no user-activation needed — Firefox guest).
  function maskComposerTextNodes() {{
    var el = getComposerEl();
    if (!el) return false;
    var walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT, null);
    var n, changed = false;
    while ((n = walker.nextNode())) {{
      var v = n.nodeValue;
      if (!v) continue;
      var m = maskStringIfPii(v);
      if (m === v) continue;
      n.nodeValue = m;
      changed = true;
    }}
    if (changed) {{
      var combined = getComposerText(el);
      var ta = document.querySelector("textarea#prompt-textarea, form textarea");
      if (ta && ta !== el) setNativeValue(ta, combined);
      notifyComposerInput(el);
    }}
    return changed;
  }}

  function setComposerText(el, text) {{
    if (!el) return;
    var tag = (el.tagName || "").toUpperCase();
    if (tag === "TEXTAREA" || tag === "INPUT") {{
      setNativeValue(el, text);
      return;
    }}
    if (maskComposerTextNodes()) return;
    try {{
      el.focus();
      var sel = window.getSelection();
      var range = document.createRange();
      range.selectNodeContents(el);
      sel.removeAllRanges();
      sel.addRange(range);
      var applied = false;
      if (IS_FIREFOX) {{
        try {{
          var dt = new DataTransfer();
          dt.setData("text/plain", text);
          el.dispatchEvent(new ClipboardEvent("paste", {{
            bubbles: true, cancelable: true, clipboardData: dt
          }}));
          applied = getComposerText(el).indexOf("***") >= 0;
        }} catch (pasteErr) {{ applied = false; }}
      }}
      if (!applied) {{
        document.execCommand("selectAll", false, null);
        applied = document.execCommand("insertText", false, text);
      }}
      if (!applied) el.textContent = text;
    }} catch (err) {{
      try {{ el.textContent = text; }} catch (e2) {{}}
    }}
    notifyComposerInput(el);
  }}

  function maskPromptState() {{
    if (maskComposerTextNodes()) return true;
    var el = getComposerEl();
    var raw = getComposerText(el);
    if (!looksLikePii(raw)) return false;
    var masked = maskText(raw);
    if (masked === raw) return false;
    setComposerText(el, masked);
    var ta = document.querySelector("textarea#prompt-textarea, form textarea");
    if (ta && ta !== el) setNativeValue(ta, masked);
    return true;
  }}

  function isSendControl(node) {{
    if (!node || !node.closest) return false;
    return !!node.closest(
      'button[data-testid="send-button"], button[aria-label*="Send"], '
      + 'button[aria-label*="send"], [data-testid="fruitjuice-send-button"], '
      + 'button[type="submit"], [data-testid="composer"] button, '
      + '[data-testid="composer-trailing-actions"] button'
    );
  }}

  function maskValueTree(value) {{
    if (typeof value === "string") {{
      if (!looksLikePii(value)) return {{ v: value, n: 0 }};
      var m = maskText(value);
      return {{ v: m, n: m === value ? 0 : 1 }};
    }}
    if (Array.isArray(value)) {{
      var total = 0, arr = [];
      for (var i = 0; i < value.length; i++) {{
        var r = maskValueTree(value[i]);
        arr.push(r.v); total += r.n;
      }}
      return {{ v: arr, n: total }};
    }}
    if (value && typeof value === "object") {{
      var total2 = 0, out = {{}};
      for (var k in value) {{
        if (!Object.prototype.hasOwnProperty.call(value, k)) continue;
        if (k === "id" || k === "parent_message_id" || k === "conversation_id") {{ out[k] = value[k]; continue; }}
        var r2 = maskValueTree(value[k]);
        out[k] = r2.v; total2 += r2.n;
      }}
      return {{ v: out, n: total2 }};
    }}
    return {{ v: value, n: 0 }};
  }}

  function maskRequestBody(body) {{
    if (body == null || typeof body !== "string") return body;
    if (!looksLikePii(body)) return body;
    try {{
      var parsed = JSON.parse(body);
      var res = maskValueTree(parsed);
      if (res.n) return JSON.stringify(res.v);
    }} catch (e) {{}}
    return maskText(body);
  }}

  function shouldHookUrl(url) {{
    var u = String(url || "").toLowerCase();
    return u.indexOf("conversation") >= 0 || u.indexOf("completion") >= 0
      || u.indexOf("prompt-autocomplete") >= 0 || u.indexOf("unauth-mweb") >= 0
      || u.indexOf("/backend-api/") >= 0 || u.indexOf("/backend-anon/") >= 0
      || u.indexOf("/v1/messages") >= 0;
  }}

  function beforeOutbound() {{
    maskPromptState();
  }}

  try {{
    var origFetch = window.fetch;
    window.fetch = async function (input, init) {{
      try {{
        var url = typeof input === "string" ? input : (input && input.url) || "";
        var method = ((init && init.method) || (input && input.method) || "GET").toUpperCase();
        if ((method === "POST" || method === "PUT" || method === "PATCH") && shouldHookUrl(url)) {{
          beforeOutbound();
          if (init && typeof init.body === "string" && looksLikePii(init.body)) {{
            init = Object.assign({{}}, init, {{ body: maskRequestBody(init.body) }});
          }} else if (typeof Request !== "undefined" && input instanceof Request) {{
            try {{
              var rb = await input.clone().text();
              if (looksLikePii(rb)) {{
                var mb = maskRequestBody(rb);
                if (mb !== rb) input = new Request(input, {{ body: mb }});
              }}
            }} catch (e) {{}}
          }}
        }}
      }} catch (e) {{}}
      return origFetch.call(this, input, init);
    }};
  }} catch (e) {{}}

  try {{
    var origOpen = XMLHttpRequest.prototype.open;
    var origSend = XMLHttpRequest.prototype.send;
    XMLHttpRequest.prototype.open = function (method, url) {{
      this.__aispmMethod = method;
      this.__aispmUrl = url;
      return origOpen.apply(this, arguments);
    }};
    XMLHttpRequest.prototype.send = function (body) {{
      try {{
        var method = String(this.__aispmMethod || "GET").toUpperCase();
        var url = this.__aispmUrl || "";
        if ((method === "POST" || method === "PUT" || method === "PATCH") && shouldHookUrl(url)) {{
          beforeOutbound();
          if (typeof body === "string" && looksLikePii(body)) body = maskRequestBody(body);
        }}
      }} catch (e) {{}}
      return origSend.call(this, body);
    }};
  }} catch (e) {{}}

  document.addEventListener("pointerdown", function (e) {{
    if (isSendControl(e.target)) beforeOutbound();
  }}, true);
  document.addEventListener("mousedown", function (e) {{
    if (isSendControl(e.target)) beforeOutbound();
  }}, true);
  document.addEventListener("click", function (e) {{
    if (isSendControl(e.target)) beforeOutbound();
  }}, true);
  document.addEventListener("keydown", function (e) {{
    if (e.key === "Enter" && !e.shiftKey) beforeOutbound();
  }}, true);
  document.addEventListener("keypress", function (e) {{
    if (e.key === "Enter" && !e.shiftKey) beforeOutbound();
  }}, true);
  document.addEventListener("submit", function () {{ beforeOutbound(); }}, true);
  document.addEventListener("input", beforeOutbound, true);
  document.addEventListener("paste", beforeOutbound, true);

  setInterval(function () {{
    var el = getComposerEl();
    if (!el) return;
    maskComposerTextNodes();
  }}, 80);

  function attachComposerObserver() {{
    var el = getComposerEl();
    if (!el || el.__aispmObserved) return;
    el.__aispmObserved = true;
    try {{
      new MutationObserver(function () {{
        maskComposerTextNodes();
      }}).observe(el, {{ childList: true, subtree: true, characterData: true }});
    }} catch (e) {{}}
  }}
  setInterval(attachComposerObserver, 250);

  try {{
    console.info("[AI-SPM] guest page mask active"
      + (IS_FIREFOX ? " (Firefox)" : IS_CHROME ? " (Chrome/Chromium)" : " (other)"));
  }} catch (e) {{}}
}})();"""


def build_ui_redact_script(enabled: frozenset[str]) -> str:
    """External script first (Chrome Trusted Types), then inline backup (Firefox CSP)."""
    body = build_ui_redact_script_body(enabled)
    return (
        f'\n<script src="{AISPM_HOOK_PATH}" data-aispm-ui-mask="1"></script>\n'
        f'<script data-aispm-ui-mask="1">\n{body}\n</script>\n'
    )



class WebUiPiiMasker:
    def responseheaders(self, flow: http.HTTPFlow) -> None:
        """Stream AI answers; strip CSP so guest page hooks can run."""
        if not is_web_ui_host(flow.request.host):
            return
        if not flow.response:
            return
        if should_stream_response(flow):
            flow.response.stream = True
            return
        ct = flow.response.headers.get("content-type", "").lower()
        if "text/html" in ct:
            for h in (
                "content-security-policy",
                "content-security-policy-report-only",
                "x-content-security-policy",
                # Chrome guest: these block injected page hooks.
                "trusted-types",
                "require-trusted-types-for",
            ):
                if h in flow.response.headers:
                    del flow.response.headers[h]

    def request(self, flow: http.HTTPFlow) -> None:
        if is_web_ui_host(flow.request.host):
            hook_path = (flow.request.path or "").split("?", 1)[0]
            # Chrome often registers a SW that serves unhooked HTML — block it.
            path_l = hook_path.lower()
            if flow.request.method == "GET" and (
                "service-worker" in path_l
                or path_l.endswith("/sw.js")
                or path_l.endswith("/serviceworker.js")
                or "/sw/" in path_l and path_l.endswith(".js")
            ):
                flow.response = http.Response.make(
                    404,
                    b"AI-SPM blocked service worker",
                    {"Content-Type": "text/plain", "Cache-Control": "no-store"},
                )
                ctx.log.warn(
                    f"[AI-SPM] blocked service worker {flow.request.pretty_url}"
                )
                return
            if flow.request.method == "GET" and hook_path == AISPM_HOOK_PATH:
                enabled = load_enabled_entities()
                js_body = build_ui_redact_script_body(enabled)
                flow.response = http.Response.make(
                    200,
                    js_body.encode("utf-8"),
                    {
                        "Content-Type": "application/javascript; charset=utf-8",
                        "Cache-Control": "no-store",
                    },
                )
                ctx.log.warn(
                    f"[AI-SPM] served guest page hook script GET {flow.request.pretty_url}"
                )
                return

        if not is_web_ui_host(flow.request.host):
            return
        if flow.request.method not in ("POST", "PUT", "PATCH"):
            return
        if not should_scan_path(flow.request.path):
            return

        raw = flow.request.get_text(strict=False)
        if raw is None:
            data = flow.request.raw_content or b""
            if len(data) > MAX_SCAN_BYTES:
                return
            try:
                raw = data.decode("utf-8", errors="replace")
            except Exception:
                return
        if not raw or len(raw) > MAX_SCAN_BYTES:
            return

        enabled = load_enabled_entities()
        provider = provider_from_host(flow.request.host)
        user_prompt = extract_user_prompt(raw, flow.request.host)

        path_l = (flow.request.path or "").lower()
        is_guest_send = (
            ("unauth-mweb" in path_l or "backend-anon" in path_l)
            and "conversation" in path_l
        )

        if not user_prompt and not looks_like_pii(raw):
            if is_guest_send and "@" not in normalize_escaped_pii(raw):
                ctx.log.warn(
                    f"[AI-SPM] guest send encrypted body on {flow.request.path[:90]} "
                    f"(len={len(raw)}) — composer must be masked before send"
                )
            return

        t0 = time.perf_counter()
        masked_body, hit_count, entities = mask_raw_body(raw, enabled)

        if hit_count == 0 and looks_like_pii(raw) and enabled and "EMAIL_ADDRESS" in enabled:
            masked_body, hit_count, entities = mask_pii(
                normalize_escaped_pii(raw), enabled
            )

        elapsed_ms = (time.perf_counter() - t0) * 1000.0

        if should_audit_path(flow.request.path) and user_prompt:
            masked_prompt, p_hits, p_ents = mask_pii(user_prompt, enabled)
            report_web_audit(
                provider=provider,
                masked_prompt=masked_prompt,
                original_prompt=user_prompt,
                entities=p_ents,
                hit_count=p_hits,
            )

        if hit_count == 0 and "conversation" in path_l and "@" not in normalize_escaped_pii(raw):
            ctx.log.warn(
                f"[AI-SPM] guest send has no plaintext PII in {flow.request.path[:90]} "
                f"(len={len(raw)} enc={'gAAAAA' in raw[:200]}) — page hook must mask composer first"
            )
            return

        if hit_count == 0:
            return

        flow.request.set_text(masked_body)
        if "content-length" in flow.request.headers:
            del flow.request.headers["content-length"]
        ctx.log.warn(
            f"[AI-SPM] Masked {hit_count} PII hit(s) in "
            f"{flow.request.method} {flow.request.pretty_url} ({elapsed_ms:.2f}ms)"
        )

    def response(self, flow: http.HTTPFlow) -> None:
        if not is_web_ui_host(flow.request.host) or not flow.response:
            return
        if getattr(flow.response, "stream", False):
            return

        content_type = flow.response.headers.get("content-type", "").lower()
        enabled = load_enabled_entities()

        if "text/html" in content_type:
            html = flow.response.get_text(strict=False)
            if not html or "data-aispm-ui-mask" in html or AISPM_HOOK_PATH in html:
                return
            if len(html) < 500:
                return
            # Strip meta CSP tags that block inline hooks (Firefox enforces these strictly).
            html = re.sub(
                r"<meta[^>]+http-equiv=[\"']?"
                r"Content-Security-Policy(?:-Report-Only)?"
                r"[\"']?[^>]*>",
                "",
                html,
                flags=re.IGNORECASE,
            )
            lower = html.lower()
            script = build_ui_redact_script(enabled)
            # Inject as early as possible so fetch hooks beat page scripts.
            idx = lower.find("<head>")
            if idx >= 0:
                insert_at = idx + len("<head>")
                html = html[:insert_at] + script + html[insert_at:]
            else:
                needle = "</head>"
                idx = lower.find(needle)
                if idx < 0:
                    needle = "</body>"
                    idx = lower.rfind(needle)
                if idx >= 0:
                    html = html[:idx] + script + html[idx:]
                else:
                    return
            flow.response.set_text(html)
            if "content-length" in flow.response.headers:
                del flow.response.headers["content-length"]
            # Prevent Firefox from serving a cached page without the hook.
            flow.response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
            flow.response.headers.pop("Pragma", None)
            ctx.log.warn(
                f"[AI-SPM] injected page hook into {flow.request.method} "
                f"{flow.request.pretty_url} (guest/incognito composer mask)"
            )
            return

        if flow.request.method != "GET":
            return
        if "application/json" not in content_type:
            return
        if not should_scan_path(flow.request.path):
            return
        if not enabled:
            return
        raw = flow.response.get_text(strict=False)
        if not raw or len(raw) > MAX_SCAN_BYTES:
            return
        masked, hit_count, _ents = mask_raw_body(raw, enabled)
        if hit_count == 0:
            return
        flow.response.set_text(masked)
        if "content-length" in flow.response.headers:
            del flow.response.headers["content-length"]

    def websocket_message(self, flow: http.HTTPFlow) -> None:
        if not is_web_ui_host(flow.request.host):
            return
        if flow.websocket is None or not flow.websocket.messages:
            return
        enabled = load_enabled_entities()
        if not enabled:
            return
        msg = flow.websocket.messages[-1]
        if not msg.from_client:
            return
        try:
            if isinstance(msg.content, (bytes, bytearray)):
                if len(msg.content) > MAX_SCAN_BYTES:
                    return
                text = msg.content.decode("utf-8", errors="replace")
            else:
                text = str(msg.content)
        except Exception:
            return
        if "@" not in text and not looks_like_pii(text):
            return
        masked, n, _ents = mask_raw_body(text, enabled)
        if n == 0 and "@" in text:
            masked, n, _ents = mask_pii(text, enabled)
        if n == 0:
            return
        msg.content = masked.encode("utf-8")


addons = [WebUiPiiMasker()]
