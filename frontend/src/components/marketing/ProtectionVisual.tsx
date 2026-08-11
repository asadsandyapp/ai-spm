/** Hero product visual — dense HTML composition that fills the hero column */
export function ProtectionVisual() {
  return (
    <div className="relative w-full">
      <div
        className="pointer-events-none absolute -inset-8 animate-pulse-glow rounded-[2.5rem] opacity-90"
        style={{
          background:
            "radial-gradient(ellipse 75% 65% at 55% 45%, rgba(45,212,191,0.22), transparent 70%)",
        }}
      />

      <div className="mkt-panel relative w-full p-5 sm:p-6 lg:p-7">
        <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-teal-400/55 to-transparent" />

        {/* Status bar */}
        <div className="mb-5 flex flex-wrap items-center justify-between gap-3 border-b border-white/10 pb-4">
          <div className="flex items-center gap-2.5">
            <span className="relative flex h-2.5 w-2.5">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-teal-400 opacity-40" />
              <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-teal-400" />
            </span>
            <span className="text-[15px] font-semibold text-white">Live inspection</span>
          </div>
          <span className="rounded-lg bg-teal-400/10 px-3 py-1 text-sm font-medium text-teal-300 ring-1 ring-teal-400/25">
            Mask before send
          </span>
        </div>

        {/* Flow stages */}
        <div className="grid gap-3 sm:grid-cols-3">
          <div className="rounded-xl border border-rose-400/25 bg-rose-500/[0.07] p-4">
            <p className="text-xs font-semibold uppercase tracking-wider text-rose-300/90">
              Outbound prompt
            </p>
            <pre className="mt-3 overflow-hidden font-mono text-[13px] leading-relaxed text-slate-300">
              <span className="text-slate-500">user@endpoint</span>
              {"\n"}
              <span className="text-rose-300">SSN: 123-45-6789</span>
              {"\n"}
              <span className="text-rose-300">jane@corp.com</span>
            </pre>
          </div>

          <div className="relative flex flex-col justify-center rounded-xl border border-teal-400/35 bg-teal-400/[0.08] p-4 text-center">
            <div className="mx-auto mb-3 grid h-14 w-14 place-items-center rounded-2xl bg-marketing-ink ring-1 ring-teal-400/50">
              <svg viewBox="0 0 32 32" className="h-7 w-7 text-teal-400" aria-hidden>
                <path
                  d="M16 3 L27 9.5 V22.5 L16 29 L5 22.5 V9.5 Z"
                  fill="currentColor"
                  fillOpacity="0.15"
                  stroke="currentColor"
                  strokeWidth="1.75"
                />
                <path
                  d="M11 16.5 L14.5 20 L21.5 12.5"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
            </div>
            <p className="font-display text-lg font-bold text-white">AI-SPM</p>
            <p className="mt-1 text-sm text-teal-200/90">Inspect · Mask · Protect</p>
            <div className="pointer-events-none absolute inset-x-6 top-0 h-full overflow-hidden rounded-xl opacity-40">
              <div className="h-8 w-full animate-scan-sweep bg-gradient-to-b from-transparent via-teal-400/50 to-transparent" />
            </div>
          </div>

          <div className="rounded-xl border border-teal-400/25 bg-white/[0.03] p-4">
            <p className="text-xs font-semibold uppercase tracking-wider text-teal-300/90">
              Provider sees
            </p>
            <pre className="mt-3 overflow-hidden font-mono text-[13px] leading-relaxed text-slate-300">
              <span className="text-slate-500">masked · safe</span>
              {"\n"}
              <span className="text-teal-300">SSN: [SSN]</span>
              {"\n"}
              <span className="text-teal-300">[EMAIL]</span>
            </pre>
          </div>
        </div>

        {/* Pipeline chips */}
        <div className="mt-5 flex flex-wrap gap-2">
          {["Inspect", "Mask", "Policy", "Audit", "Forward"].map((step, i) => (
            <div
              key={step}
              className="flex items-center gap-2 rounded-lg border border-white/10 bg-white/[0.04] px-3.5 py-2.5"
            >
              <span className="font-mono text-xs tabular-nums text-teal-400/80">
                {String(i + 1).padStart(2, "0")}
              </span>
              <span className="text-[15px] font-medium text-slate-100">{step}</span>
            </div>
          ))}
        </div>

        <p className="mt-5 text-[15px] leading-relaxed text-slate-400">
          Protects AI apps and ChatGPT, Claude, and Gemini in the browser — without a managed
          browser extension for employees.
        </p>
      </div>
    </div>
  );
}
