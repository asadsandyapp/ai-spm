(function () {
  "use strict";
  if (window.__aispmHookInstalled) return;
  window.__aispmHookInstalled = true;

  const TIMEOUT_MS = 5000;
  let seq = 0;
  const pending = new Map();

  // Visible in DevTools console — confirms content scripts injected on this frame.
  try {
    console.info("[AI-SPM] Prompt Guard hooks active on", location.hostname);
  } catch (_) {}

  window.addEventListener("message", (event) => {
    if (event.source !== window) return;
    const data = event.data;
    if (!data || data.__aispm !== "response") return;
    const resolve = pending.get(data.id);
    if (resolve) {
      pending.delete(data.id);
      resolve(data.result || { decision: "allowed" });
    }
  });

  // Tell the agent this page frame loaded hooks (shows up in agent.log).
  try {
    window.postMessage(
      {
        __aispm: "request",
        id: ++seq,
        mode: "hook_alive",
        host: location.hostname,
      },
      "*",
    );
  } catch (_) {}

  function inspectRaw(host, path, method, body) {
    return new Promise((resolve) => {
      const id = ++seq;
      pending.set(id, resolve);
      window.postMessage(
        { __aispm: "request", id, mode: "raw", host, path, method, body },
        "*",
      );
      setTimeout(() => {
        if (pending.has(id)) {
          pending.delete(id);
          resolve({
            decision: "blocked",
            blocked: true,
            blocked_reason:
              "AI-SPM inspect timed out — restart agent: sudo systemctl restart ai-spm-agent",
          });
        }
      }, TIMEOUT_MS);
    });
  }

  function inspect(provider, messages, model) {
    return new Promise((resolve) => {
      const id = ++seq;
      pending.set(id, resolve);
      window.postMessage({ __aispm: "request", id, provider, model, messages }, "*");
      setTimeout(() => {
        if (pending.has(id)) {
          pending.delete(id);
          // Fail-open on timeout so Claude/Gemini keep working if the agent is slow/down.
          resolve({ decision: "allowed" });
        }
      }, TIMEOUT_MS);
    });
  }

  function isGeminiPage() {
    try {
      const h = window.location.hostname.toLowerCase();
      return h === "gemini.google.com" || h.endsWith(".gemini.google.com");
    } catch (_) {
      return false;
    }
  }

  function isClaudePage() {
    try {
      const h = window.location.hostname.toLowerCase();
      return h === "claude.ai" || h.endsWith(".claude.ai");
    } catch (_) {
      return false;
    }
  }

  function isChatGPTPage() {
    try {
      const h = window.location.hostname.toLowerCase();
      return (
        h === "chatgpt.com" ||
        h.endsWith(".chatgpt.com") ||
        h === "chat.openai.com" ||
        h.endsWith(".openai.com")
      );
    } catch (_) {
      return false;
    }
  }

  /** Infer provider from request URL, falling back to the page host for relative APIs. */
  function detectProvider(url) {
    const u = (url || "").toLowerCase();
    if (u.includes("openai.com") || u.includes("chatgpt.com")) return "openai";
    if (u.includes("claude.ai") || u.includes("anthropic.com")) return "anthropic";
    if (
      u.includes("gemini.google.com") ||
      u.includes("generativelanguage.googleapis.com") ||
      u.includes("bard.google.com")
    ) {
      return "gemini";
    }
    // Claude/ChatGPT often POST to same-origin relative paths (/api/..., /backend-api/...)
    // that do not include the product hostname — use the page frame instead.
    if (isClaudePage()) return "anthropic";
    if (isGeminiPage()) return "gemini";
    if (isChatGPTPage()) return "openai";
    return "openai";
  }

  /** True when this POST likely carries user prompt text. */
  function shouldInspect(url, method) {
    if (!url || (method || "GET").toUpperCase() !== "POST") return false;
    const u = url.toLowerCase();
    const onGemini = isGeminiPage() || u.includes("gemini.google.com");
    const onClaude =
      isClaudePage() ||
      u.includes("claude.ai") ||
      u.includes("anthropic.com");

    // Gemini web: only StreamGenerate. Ignore batchexecute telemetry entirely.
    if (onGemini && u.includes("streamgenerate")) {
      return true;
    }

    // Claude web UI + a-api.anthropic.com (fetch often originates from a.claude.ai iframe).
    if (onClaude && (
      u.includes("completion") ||
      u.includes("/api/messages") ||
      u.includes("/api/chat") ||
      u.includes("/chat_conversations/") ||
      u.includes("/api/organizations/") ||
      u.includes("/v1/messages") ||
      u.includes("/v1/complete") ||
      u.includes("append_message") ||
      u.includes("/chat_conversations")
    )) {
      return true;
    }

    return (
      // ChatGPT web UI (backend-api, backend-anon, /f/conversation, prepare)
      ((u.includes("/backend-api/") || u.includes("/backend-anon/")) &&
        (u.includes("conversation") || u.includes("completion") || u.includes("/f/"))) ||
      ((u.includes("chatgpt.com") || u.includes("chat.openai.com") || u.includes("openai.com")) &&
        u.includes("/backend-") &&
        (u.includes("conversation") || u.includes("prepare") || u.includes("/f/"))) ||
      // Claude web UI (relative or absolute URLs)
      (u.includes("/chat_conversations/") && u.includes("completion")) ||
      (u.includes("/api/organizations/") && u.includes("completion")) ||
      // Anthropic / OpenAI APIs (including a-api.anthropic.com)
      u.includes("/v1/messages") ||
      u.includes("/v1/chat/completions") ||
      // Gemini REST API (non-web)
      u.includes("generatecontent")
    );
  }

  async function bodyToText(body) {
    if (body == null) return null;
    if (typeof body === "string") return body;
    if (body instanceof URLSearchParams) return body.toString();
    if (body instanceof FormData) {
      const parts = [];
      for (const [key, value] of body.entries()) {
        const text =
          typeof value === "string" ? value : value instanceof Blob ? await value.text() : String(value);
        parts.push(encodeURIComponent(key) + "=" + encodeURIComponent(text));
      }
      return parts.join("&");
    }
    if (body instanceof Blob) return body.text();
    if (body instanceof ArrayBuffer) return new TextDecoder().decode(body);
    if (ArrayBuffer.isView(body)) return new TextDecoder().decode(body);
    try {
      return String(body);
    } catch (_) {
      return null;
    }
  }

  function extractPromptRefs(json) {
    const refs = [];
    function pushPartRef(parts, i) {
      if (typeof parts[i] === "string" && parts[i].length) {
        refs.push({ get: () => parts[i], set: (v) => { parts[i] = v; } });
      } else if (parts[i] && typeof parts[i].text === "string" && parts[i].text.length) {
        refs.push({
          get: () => parts[i].text,
          set: (v) => { parts[i].text = v; },
        });
      }
    }

    // ChatGPT web UI — single outgoing message
    if (json.message && json.message.content && Array.isArray(json.message.content.parts)) {
      const parts = json.message.content.parts;
      for (let i = 0; i < parts.length; i++) pushPartRef(parts, i);
    }
    if (Array.isArray(json.messages)) {
      for (const m of json.messages) {
        const role = (m && m.author && m.author.role) || (m && m.role) || "user";
        if (role !== "user" && role !== "human") continue;

        if (m && m.content && Array.isArray(m.content.parts)) {
          const parts = m.content.parts;
          for (let i = 0; i < parts.length; i++) pushPartRef(parts, i);
        } else if (m && m.content && Array.isArray(m.content)) {
          // Anthropic API / Claude: content = [{type:"text", text:"..."}]
          for (const block of m.content) {
            if (block && block.type === "text" && typeof block.text === "string" && block.text.length) {
              refs.push({ get: () => block.text, set: (v) => { block.text = v; } });
            }
          }
        } else if (m && typeof m.content === "string" && m.content.length) {
          refs.push({ get: () => m.content, set: (v) => { m.content = v; } });
        }
      }
    }
    if (typeof json.prompt === "string" && json.prompt.length) {
      refs.push({ get: () => json.prompt, set: (v) => { json.prompt = v; } });
    }
    // Claude web UI — root prompt field (common on /api/ completion)
    if (typeof json.input === "string" && json.input.length) {
      refs.push({ get: () => json.input, set: (v) => { json.input = v; } });
    }
    if (json.input && typeof json.input.prompt === "string" && json.input.prompt.length) {
      refs.push({ get: () => json.input.prompt, set: (v) => { json.input.prompt = v; } });
    }
    if (Array.isArray(json.input)) {
      for (const item of json.input) {
        if (item && typeof item.content === "string" && item.content.length) {
          refs.push({ get: () => item.content, set: (v) => { item.content = v; } });
        }
      }
    }
    // Gemini API generateContent
    if (Array.isArray(json.contents)) {
      for (const item of json.contents) {
        if (!item || !Array.isArray(item.parts)) continue;
        for (const part of item.parts) {
          if (part && typeof part.text === "string" && part.text.length) {
            refs.push({ get: () => part.text, set: (v) => { part.text = v; } });
          }
        }
      }
    }
    return refs;
  }

  /** True when a string looks like a real user prompt, not an RPC token/flag/id. */
  function looksLikePrompt(text) {
    if (typeof text !== "string") return false;
    const t = text.trim();
    if (t.length < 3 || t.length > 20000) return false;
    if (/^https?:\/\//i.test(t)) return false;
    // Reject JSON / RPC envelopes (Gemini batchexecute telemetry).
    if (t[0] === "[" || t[0] === "{") return false;
    // Reject base64/token blobs and long id-like strings.
    if (/^[A-Za-z0-9+/=_-]{40,}$/.test(t)) return false;
    // Reject UUIDs and request ids (r_…).
    if (/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(t)) return false;
    if (/^r_[a-z0-9]+$/i.test(t)) return false;
    // Reject locale codes / feature flags / snake identifiers with no spaces.
    if (!/\s/.test(t) && /^[A-Za-z0-9._-]+$/.test(t) && !/@/.test(t)) return false;
    // Natural language: must contain whitespace or an email-like "@".
    // (Bare tokens without spaces are almost always Gemini RPC metadata.)
    if (!(/\s/.test(t) || /@/.test(t))) return false;
    // Reject strings that are mostly punctuation / digits (serialized arrays leaked as text).
    const letters = (t.match(/[A-Za-z]/g) || []).length;
    if (letters < 3) return false;
    return true;
  }

  /**
   * Gemini web UI (observed in DevTools):
   * - User prompts → POST StreamGenerate (bl=boq_assistant-bard-web-server…),
   *   f.req = [null, "[[\"prompt\",0,null,…]]"]
   * - batchexecute?rpcids=ESY5D|PCCk7e|… → telemetry (bard_activity_enabled, r_…);
   *   never inspect.
   */
  function isGeminiChatRpc(url, _bodyText) {
    return (url || "").toLowerCase().includes("streamgenerate");
  }

  /** Parse the inner JSON array from a Gemini f.req form value. */
  function parseGeminiInner(freq) {
    try {
      const outer = JSON.parse(freq);
      if (Array.isArray(outer) && typeof outer[1] === "string") {
        return JSON.parse(outer[1]);
      }
      // batchexecute wrapper: [[["rpcId","<inner-json-string>",null,"generic"]]]
      if (Array.isArray(outer) && Array.isArray(outer[0]) && Array.isArray(outer[0][0])) {
        const cell = outer[0][0];
        for (let i = 0; i < cell.length; i++) {
          const part = cell[i];
          if (typeof part === "string" && part.length > 1 && part[0] === "[") {
            try {
              return JSON.parse(part);
            } catch (_) {}
          }
        }
      }
    } catch (_) {}
    return null;
  }

  /** Locate the user-prompt string inside a parsed Gemini inner payload. */
  function findGeminiPromptSlot(inner) {
    if (!inner) return null;
    if (inner[0] && typeof inner[0][0] === "string" && looksLikePrompt(inner[0][0])) {
      return { container: inner[0], index: 0, text: inner[0][0] };
    }
    if (inner[0] && inner[0][0] && typeof inner[0][0][0] === "string" && looksLikePrompt(inner[0][0][0])) {
      return { container: inner[0][0], index: 0, text: inner[0][0][0] };
    }
    function walk(node, depth) {
      if (!Array.isArray(node) || depth > 8) return null;
      for (let i = 0; i < node.length; i++) {
        const v = node[i];
        if (typeof v === "string" && looksLikePrompt(v) && (/\s/.test(v) || /@/.test(v))) {
          return { container: node, index: i, text: v };
        }
        const nested = walk(v, depth + 1);
        if (nested) return nested;
      }
      return null;
    }
    return walk(inner, 0);
  }

  /**
   * Extract the user prompt from a Gemini StreamGenerate f.req payload.
   *
   * Structure: f.req = [null, "<inner-json-string>"] where
   * inner = [["<prompt text>", 0, null, [...]], ...]. We target inner[0][0]
   * precisely and fall back to a strict natural-language heuristic only if the
   * known shape changes.
   */
  function extractGeminiCandidates(freq) {
    const inner = parseGeminiInner(freq);
    if (inner) {
      const slot = findGeminiPromptSlot(inner);
      if (slot) return [slot.text];
    }
    const candidates = [];
    const seen = new Set();
    function consider(text) {
      if (!looksLikePrompt(text) || seen.has(text)) return;
      seen.add(text);
      candidates.push(text);
    }
    function walk(val) {
      if (typeof val === "string") {
        consider(val);
        try {
          walk(JSON.parse(val));
        } catch (_) {}
      } else if (Array.isArray(val)) {
        val.forEach(walk);
      } else if (val && typeof val === "object") {
        Object.values(val).forEach(walk);
      }
    }
    try {
      walk(JSON.parse(freq));
    } catch (_) {
      const re = /"((?:[^"\\]|\\.){12,})"/g;
      let m;
      while ((m = re.exec(freq))) {
        try {
          consider(JSON.parse('"' + m[1] + '"'));
        } catch (_) {
          consider(m[1]);
        }
      }
    }
    // Prefer strings containing whitespace or "@" (clear natural language / emails).
    const natural = candidates.filter((c) => /\s/.test(c) || /@/.test(c));
    const pool = natural.length ? natural : candidates;
    return pool.sort((a, b) => b.length - a.length).slice(0, 1);
  }

  async function applyInspection(provider, model, refs, bodyText) {
    if (!refs.length) return { body: bodyText };

    const result = await inspect(
      provider,
      refs.map((r) => ({ role: "user", content: r.get() })),
      model
    );

    if (result && result.decision === "blocked") {
      try {
        window.alert("AI-SPM blocked this prompt: " + (result.blocked_reason || "policy"));
      } catch (_) {}
      return { blocked: true };
    }

    if (result && Array.isArray(result.masked_messages)) {
      let changed = false;
      for (let i = 0; i < refs.length && i < result.masked_messages.length; i++) {
        const masked = result.masked_messages[i];
        const text = masked && typeof masked.content === "string" ? masked.content : null;
        if (text != null && text !== refs[i].get()) {
          refs[i].set(text);
          changed = true;
        }
      }
      if (changed) return { changed: true };
    }
    return { body: bodyText };
  }

  /** Replace ONLY the f.req parameter value in a form body, leaving every other
   *  parameter (at, _reqid, etc.) byte-for-byte intact to avoid corrupting the RPC. */
  function replaceFreqParam(bodyText, newFreqDecoded) {
    // application/x-www-form-urlencoded: spaces are "+", not "%20".
    const encoded = encodeURIComponent(newFreqDecoded).replace(/%20/g, "+");
    if (/(^|&)f\.req=/.test(bodyText)) {
      return bodyText.replace(/((^|&)f\.req=)[^&]*/, `$1${encoded}`);
    }
    return bodyText;
  }

  function decodeFormValue(v) {
    try {
      return decodeURIComponent(v.replace(/\+/g, " "));
    } catch (_) {
      return v;
    }
  }

  /** Quick sync check: does this Gemini batchexecute body carry a user prompt? */
  function geminiFreqHasPrompt(bodyText) {
    const match = bodyText.match(/(?:^|&)f\.req=([^&]*)/);
    if (!match) return false;
    try {
      const freq = decodeFormValue(match[1]);
      const inner = parseGeminiInner(freq);
      if (inner) {
        const slot = findGeminiPromptSlot(inner);
        if (slot && looksLikePrompt(slot.text)) return true;
      }
      // Fallback candidates already filtered by looksLikePrompt — require natural text.
      const candidates = extractGeminiCandidates(freq).filter(
        (c) => looksLikePrompt(c) && (/\s/.test(c) || /@/.test(c)),
      );
      return candidates.length > 0;
    } catch (_) {
      return false;
    }
  }

  /**
   * Extract + mask the user prompt from a Gemini StreamGenerate f.req payload.
   *
   * Observed shape (gemini.google.com → StreamGenerate, form-urlencoded):
   *   f.req = [null, "<inner-json-string>"]
   *   inner = [["<prompt text>", 0, null, ...], ...]
   * Telemetry batchexecute (rpcids=ESY5D / PCCk7e / …) is never passed here.
   */
  async function processGeminiBatchexecute(url, bodyText) {
    const provider = "gemini";
    const match = bodyText.match(/(?:^|&)f\.req=([^&]*)/);
    if (!match) return { body: bodyText };
    const freq = decodeFormValue(match[1]);

    // Primary: structured rewrite. f.req = [null, "<inner-json>"]; inner[0][0] is the
    // prompt. Rebuilding the JSON keeps the payload well-formed — string-replacing the
    // whole form body previously corrupted the request ("message cut off").
    try {
      const outer = JSON.parse(freq);
      const inner = parseGeminiInner(freq);
      if (inner) {
        const slot = findGeminiPromptSlot(inner);
        if (slot) {
          const original = slot.text;
          let promptText = original;
          const ref = { get: () => promptText, set: (v) => { promptText = v; } };
          const outcome = await applyInspection(provider, "gemini-1.5-pro", [ref], bodyText);
          if (outcome.blocked) return outcome;
          if (promptText !== original) {
            slot.container[slot.index] = promptText;
            // Write inner back into whichever outer shape we parsed.
            if (Array.isArray(outer) && typeof outer[1] === "string") {
              outer[1] = JSON.stringify(inner);
              return { body: replaceFreqParam(bodyText, JSON.stringify(outer)) };
            }
            if (Array.isArray(outer) && Array.isArray(outer[0]) && Array.isArray(outer[0][0])) {
              const cell = outer[0][0];
              for (let i = 0; i < cell.length; i++) {
                if (typeof cell[i] === "string" && cell[i].length > 1 && cell[i][0] === "[") {
                  cell[i] = JSON.stringify(inner);
                  return { body: replaceFreqParam(bodyText, JSON.stringify(outer)) };
                }
              }
            }
          }
          return { body: bodyText };
        }
      }
    } catch (_) {}

    // Fallback: heuristic single-candidate + targeted replacement inside f.req only.
    const candidates = extractGeminiCandidates(freq);
    if (!candidates.length) return { body: bodyText };
    const original = candidates[0];
    let current = original;
    const ref = { get: () => current, set: (v) => { current = v; } };
    const outcome = await applyInspection(provider, "gemini-1.5-pro", [ref], bodyText);
    if (outcome.blocked) return outcome;
    if (current !== original) {
      const newFreq = freq.split(original).join(current);
      return { body: replaceFreqParam(bodyText, newFreq) };
    }
    return { body: bodyText };
  }

  async function processBody(url, bodyText) {
    const provider = detectProvider(url);
    const lower = bodyText.toLowerCase();

    // Gemini batchexecute handled in interceptOutbound (not here).
    if (!isGeminiPage() && (url.includes("batchexecute") || lower.includes("f.req="))) {
      return { body: bodyText };
    }

    let json;
    try {
      json = JSON.parse(bodyText);
    } catch (_) {
      return { body: bodyText };
    }

    const refs = extractPromptRefs(json);
    const model =
      (typeof json.model === "string" && json.model) ||
      (provider === "anthropic" ? "claude-3-5-sonnet" : provider === "gemini" ? "gemini-1.5-pro" : "gpt-4o");

    const outcome = await applyInspection(provider, model, refs, bodyText);
    if (outcome.blocked) return outcome;
    if (outcome.changed) return { body: JSON.stringify(json) };
    return { body: bodyText };
  }

  function parseRequestUrl(url) {
    try {
      const u = new URL(url, window.location.href);
      return { host: u.hostname, path: u.pathname + u.search };
    } catch (_) {
      return { host: window.location.hostname, path: String(url || "") };
    }
  }

  async function interceptOutbound(url, method, body) {
    if (!shouldInspect(url, method)) return null;
    const bodyText = await bodyToText(body);
    if (!bodyText) return null;

    const u = (url || "").toLowerCase();
    const onGemini = isGeminiPage() || u.includes("gemini.google.com");

    // Gemini web: StreamGenerate only (batchexecute is telemetry — skip entirely).
    if (onGemini && (u.includes("streamgenerate") || bodyText.includes("f.req="))) {
      if (!isGeminiChatRpc(url, bodyText)) return null;
      const outcome = await processGeminiBatchexecute(url, bodyText);
      if (outcome.blocked) return outcome;
      if (outcome.body && outcome.body !== bodyText) return { body: outcome.body };
      return null;
    }

    const outcome = await processBody(url, bodyText);
    if (outcome.blocked) return outcome;
    if (outcome.body && outcome.body !== bodyText) return { body: outcome.body };
    return null;
  }

  // --- fetch hook (ChatGPT / Claude / Gemini) ---
  const originalFetch = window.fetch;
  window.fetch = async function (input, init) {
    try {
      const url = typeof input === "string" ? input : input instanceof Request ? input.url : "";
      const method = (init && init.method) || (input instanceof Request ? input.method : "GET");
      let body = init && init.body != null ? init.body : null;
      if (body == null && input instanceof Request) {
        try {
          body = await input.clone().text();
        } catch (_) {}
      }

      const outcome = await interceptOutbound(url, method, body);
      if (outcome && outcome.blocked) return Promise.reject(new Error("AI-SPM: blocked"));
      if (outcome && outcome.body) {
        try {
          console.info("[AI-SPM] masked outbound prompt for", url.slice(0, 80));
        } catch (_) {}
        if (input instanceof Request && (!init || init.body == null)) {
          input = new Request(input, { body: outcome.body });
        } else {
          init = Object.assign({}, init || {}, { body: outcome.body });
        }
      }
    } catch (err) {
      try {
        console.warn("[AI-SPM] intercept error (fail-open):", err);
      } catch (_) {}
    }
    return originalFetch.call(this, input, init);
  };

  // --- XMLHttpRequest hook (Claude web UI) ---
  const origOpen = XMLHttpRequest.prototype.open;
  const origSend = XMLHttpRequest.prototype.send;

  XMLHttpRequest.prototype.open = function (method, url) {
    this._aispmMethod = method;
    this._aispmUrl = typeof url === "string" ? url : String(url);
    return origOpen.apply(this, arguments);
  };

  XMLHttpRequest.prototype.send = function (body) {
    const xhr = this;
    const url = xhr._aispmUrl || "";
    const method = xhr._aispmMethod || "GET";

    if (!shouldInspect(url, method) || body == null) {
      return origSend.apply(xhr, arguments);
    }

    (async () => {
      try {
        const outcome = await interceptOutbound(url, method, body);
        if (outcome && outcome.blocked) {
          try {
            Object.defineProperty(xhr, "status", { value: 403 });
            Object.defineProperty(xhr, "responseText", {
              value: JSON.stringify({ detail: "AI-SPM: blocked", blocked_by: "AI-SPM" }),
            });
            xhr.dispatchEvent(new Event("error"));
          } catch (_) {}
          return;
        }
        origSend.call(xhr, outcome && outcome.body ? outcome.body : body);
      } catch (_) {
        origSend.call(xhr, body);
      }
    })();
  };
})();
