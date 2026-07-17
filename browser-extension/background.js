const DEFAULT_BASE = "http://127.0.0.1:8092";

async function baseUrl() {
  try {
    const { aispmEndpoint } = await chrome.storage.local.get("aispmEndpoint");
    const raw = aispmEndpoint || DEFAULT_BASE;
    return String(raw).replace(/\/$/, "").replace(/\/inspect$/, "");
  } catch (_) {
    return DEFAULT_BASE;
  }
}

function blocked(reason) {
  return { decision: "blocked", blocked: true, blocked_reason: reason };
}

async function inspectRaw(host, path, method, body) {
  const base = await baseUrl();
  try {
    const resp = await fetch(`${base}/v1/inspect`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ host, path, method, body }),
    });
    if (resp.ok) {
      return await resp.json();
    }
  } catch (_) {
    /* fall through to messages API */
  }
  return inspectRawViaMessages(body);
}

function extractMessagesFromRawBody(body) {
  if (!body || typeof body !== "string") return [];
  try {
    const json = JSON.parse(body);
    const refs = [];
    if (json.message && json.message.content && Array.isArray(json.message.content.parts)) {
      for (const part of json.message.content.parts) {
        if (typeof part === "string" && part.length) {
          refs.push({ role: "user", content: part });
        }
      }
    }
    if (Array.isArray(json.messages)) {
      for (const m of json.messages) {
        const role = (m && m.author && m.author.role) || (m && m.role) || "user";
        if (role !== "user" && role !== "human") continue;
        if (m && m.content && Array.isArray(m.content.parts)) {
          for (const part of m.content.parts) {
            if (typeof part === "string" && part.length) {
              refs.push({ role: "user", content: part });
            }
          }
        } else if (m && typeof m.content === "string" && m.content.length) {
          refs.push({ role: "user", content: m.content });
        }
      }
    }
    return refs;
  } catch (_) {
    return [];
  }
}

function applyMaskedToRawBody(body, maskedMessages) {
  try {
    const json = JSON.parse(body);
    let idx = 0;
    if (json.message && json.message.content && Array.isArray(json.message.content.parts)) {
      for (let i = 0; i < json.message.content.parts.length; i++) {
        const masked = maskedMessages[idx++];
        if (masked && typeof masked.content === "string") {
          json.message.content.parts[i] = masked.content;
        }
      }
      return JSON.stringify(json);
    }
    if (Array.isArray(json.messages)) {
      for (const m of json.messages) {
        const role = (m && m.author && m.author.role) || (m && m.role) || "user";
        if (role !== "user" && role !== "human") continue;
        if (m && m.content && Array.isArray(m.content.parts)) {
          for (let i = 0; i < m.content.parts.length; i++) {
            const masked = maskedMessages[idx++];
            if (masked && typeof masked.content === "string") {
              m.content.parts[i] = masked.content;
            }
          }
        } else if (m && typeof m.content === "string") {
          const masked = maskedMessages[idx++];
          if (masked && typeof masked.content === "string") {
            m.content = masked.content;
          }
        }
      }
      return JSON.stringify(json);
    }
  } catch (_) {}
  return body;
}

async function inspectRawViaMessages(body) {
  const messages = extractMessagesFromRawBody(body);
  if (!messages.length) {
    return blocked("AI-SPM could not parse prompt from request body.");
  }
  const result = await inspectMessages("openai", "gpt-4o", messages);
  if (!result) {
    return blocked(
      "AI-SPM inspect API unavailable. Run: sudo ./scripts/install-agent.sh",
    );
  }
  if (result.decision === "blocked") {
    return result;
  }
  if (Array.isArray(result.masked_messages)) {
    return {
      decision: result.decision || "masked",
      body: applyMaskedToRawBody(body, result.masked_messages),
    };
  }
  return result;
}

async function inspectMessages(provider, model, messages) {
  const base = await baseUrl();
  try {
    const resp = await fetch(`${base}/inspect`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ provider, model, messages }),
    });
    if (!resp.ok) {
      return null;
    }
    return await resp.json();
  } catch (_) {
    return null;
  }
}

async function reportHookAlive(host) {
  const base = await baseUrl();
  try {
    const resp = await fetch(
      `${base}/extension/hook-ping?host=${encodeURIComponent(host || "")}`,
      { method: "GET", cache: "no-store" },
    );
    return resp.ok;
  } catch (err) {
    try {
      console.warn("[AI-SPM] hook-ping failed — is ai-spm-agent running on :8092?", err);
    } catch (_) {}
    return false;
  }
}

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (!msg) return false;

  if (msg.type === "hook_alive") {
    (async () => {
      sendResponse({ ok: await reportHookAlive(msg.host) });
    })();
    return true;
  }

  if (msg.type === "inspect_raw") {
    (async () => {
      sendResponse(
        await inspectRaw(msg.host, msg.path, msg.method, msg.body),
      );
    })();
    return true;
  }

  if (msg.type === "inspect") {
    (async () => {
      const result = await inspectMessages(
        msg.provider || "openai",
        msg.model || "gpt-4o",
        msg.messages || [],
      );
      if (result) {
        sendResponse(result);
        return;
      }
      // Fail-open when agent inspect API is down — masking is skipped, chat still works.
      try {
        console.warn(
          "[AI-SPM] inspect API unavailable — fail-open (prompt NOT masked). Check: systemctl status ai-spm-agent",
        );
      } catch (_) {}
      sendResponse({ decision: "allowed" });
    })();
    return true;
  }

  return false;
});
