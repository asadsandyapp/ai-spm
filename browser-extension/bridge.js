window.addEventListener("message", (event) => {
  if (event.source !== window) return;
  const data = event.data;
  if (!data || data.__aispm !== "request") return;

  let payload;
  if (data.mode === "raw") {
    payload = {
      type: "inspect_raw",
      host: data.host,
      path: data.path,
      method: data.method,
      body: data.body,
    };
  } else if (data.mode === "hook_alive") {
    payload = { type: "hook_alive", host: data.host || "" };
  } else {
    payload = {
      type: "inspect",
      provider: data.provider,
      model: data.model,
      messages: data.messages,
    };
  }

  chrome.runtime.sendMessage(payload, (result) => {
    if (chrome.runtime.lastError) {
      try {
        console.warn("[AI-SPM] bridge error:", chrome.runtime.lastError.message);
      } catch (_) {}
    }
    if (data.mode === "hook_alive") return;
    window.postMessage(
      {
        __aispm: "response",
        id: data.id,
        // Fail-open when the agent/background is unavailable so Claude/Gemini keep working.
        result: result || { decision: "allowed" },
      },
      "*",
    );
  });
});
