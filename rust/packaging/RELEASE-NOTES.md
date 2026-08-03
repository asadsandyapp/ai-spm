## AI-SPM DLP Agent

A local Windows agent that intercepts your traffic to AI chat services
(ChatGPT, Claude, Gemini) and masks or blocks sensitive data (card numbers,
CNICs, SSNs, emails, API keys, and more) before it leaves your machine.
Everything else you browse is untouched — only the configured AI-service
domains are ever routed through it.

### Install

1. Download `AI-SPM-DLP-Agent-<version>.zip` below and unzip it.
2. Run the `.msi` inside. Approve the SmartScreen warning ("More info" →
   "Run anyway" — the installer isn't code-signed yet) and the one
   Administrator/UAC prompt that follows.
3. Read `INSTALL-NOTES.txt` (bundled in the zip) for the one remaining
   per-user step (`agentctl enable-proxy`, no admin needed) and how to
   verify it's working.

Full usage guide and troubleshooting: see
[`USAGE.md`](https://github.com/asadsandyapp/ai-spm/blob/rust/USAGE.md).
Architecture and internals: see
[`README.md`](https://github.com/asadsandyapp/ai-spm/blob/rust/README.md).

### What's changed in this release
