import { useState } from "react";
import {
  Check,
  Copy,
  Download,
  KeyRound,
  RefreshCw,
  Server,
} from "lucide-react";
import {
  ErrorState,
  PageHeader,
  Spinner,
} from "@/components/ui/States";
import {
  useDownloadLinuxInstaller,
  useEnrollment,
  useRotateOrgToken,
} from "@/hooks/queries";
import { ApiError } from "@/lib/api";

function maskToken(token: string): string {
  if (token.length <= 12) return "•".repeat(token.length);
  return `${token.slice(0, 8)}…${token.slice(-4)}`;
}

export function DownloadAgentPage() {
  const { data, isLoading, isError, error, refetch, isFetching } = useEnrollment();
  const rotateM = useRotateOrgToken();
  const downloadM = useDownloadLinuxInstaller();

  const [revealedToken, setRevealedToken] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionHint, setActionHint] = useState<string | null>(null);

  async function copyText(text: string) {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      setActionError("Could not copy to clipboard.");
    }
  }

  async function handleRotate() {
    setActionError(null);
    setActionHint(null);
    try {
      const res = await rotateM.mutateAsync();
      setRevealedToken(res.org_token);
      setActionHint(
        "New org token generated. Copy it now — it will not be shown again after you leave this page.",
      );
    } catch (err) {
      setActionError(
        err instanceof ApiError ? err.detail : "Failed to rotate org token.",
      );
    }
  }

  async function handleDownload() {
    setActionError(null);
    setActionHint(null);
    try {
      const { blob, orgToken, filename } = await downloadM.mutateAsync();
      if (orgToken) setRevealedToken(orgToken);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      setActionHint(
        "Sealed installer downloaded (.run). Share that single file — scripts and tokens are embedded, not an editable folder. Download rotates the enrollment token.",
      );
    } catch (err) {
      setActionError(
        err instanceof ApiError
          ? err.detail
          : "Failed to download the Linux installer package.",
      );
    }
  }

  if (isLoading) {
    return (
      <div className="flex min-h-[40vh] items-center justify-center">
        <Spinner />
      </div>
    );
  }

  if (isError || !data) {
    return (
      <ErrorState
        error={
          error instanceof ApiError
            ? error
            : new Error("Could not load agent enrollment details.")
        }
        onRetry={() => void refetch()}
      />
    );
  }

  return (
    <div className="space-y-6 animate-fade-in">
      <PageHeader
        title="Download Agent"
        description="Download a sealed single-file Linux installer for employees. Org token and gateway URL are embedded so installs register into this organization only."
        actions={
          <button
            type="button"
            className="btn-secondary"
            onClick={() => void refetch()}
            disabled={isFetching}
          >
            <RefreshCw
              className={`h-4 w-4 ${isFetching ? "animate-spin" : ""}`}
            />
            Refresh
          </button>
        }
      />

      {(actionError || actionHint) && (
        <div
          className={
            actionError
              ? "rounded-lg border border-danger-200 bg-danger-50 px-4 py-3 text-sm text-danger-800"
              : "rounded-lg border border-brand-200 bg-brand-50 px-4 py-3 text-sm text-brand-900"
          }
        >
          {actionError ?? actionHint}
        </div>
      )}

      <div className="grid gap-4 md:grid-cols-3">
        <div className="card p-5">
          <p className="text-xs font-medium uppercase tracking-wide text-ink-500">
            Organization
          </p>
          <p className="mt-2 text-lg font-semibold text-ink-900">{data.org_name}</p>
          <p className="mt-1 font-mono text-xs text-ink-500">{data.org_slug}</p>
        </div>
        <div className="card p-5 md:col-span-2">
          <p className="text-xs font-medium uppercase tracking-wide text-ink-500">
            Gateway URL
          </p>
          <p className="mt-2 break-all font-mono text-sm text-ink-900">
            {data.gateway_url}
          </p>
          <p className="mt-2 text-xs text-ink-500">
            Stamped into enrollment.env. For cloud, set AISPM_PUBLIC_GATEWAY_URL on
            the API host and re-download.
          </p>
        </div>
      </div>

      <div className="card overflow-hidden">
        <div className="border-b border-ink-200 px-5 py-4">
          <h2 className="flex items-center gap-2 text-base font-semibold text-ink-900">
            <KeyRound className="h-4 w-4 text-brand-600" />
            Organization enrollment token
          </h2>
          <p className="mt-1 text-sm text-ink-500">
            Stored hashed at rest. Rotate to obtain a plaintext token, or download
            the Linux package (download also rotates and embeds a fresh token).
          </p>
        </div>
        <div className="space-y-4 p-5">
          <div className="flex flex-wrap items-center gap-3">
            <code className="rounded-md bg-ink-100 px-3 py-2 font-mono text-sm text-ink-800">
              {revealedToken
                ? maskToken(revealedToken)
                : data.has_token
                  ? "•••••••• (token on file — rotate or download to reveal)"
                  : "No token — rotate or download to create one"}
            </code>
            {revealedToken && (
              <button
                type="button"
                className="btn-secondary"
                onClick={() => void copyText(revealedToken)}
              >
                {copied ? (
                  <Check className="h-4 w-4 text-success-600" />
                ) : (
                  <Copy className="h-4 w-4" />
                )}
                {copied ? "Copied" : "Copy full token"}
              </button>
            )}
            <button
              type="button"
              className="btn-secondary"
              disabled={rotateM.isPending}
              onClick={() => void handleRotate()}
            >
              <RefreshCw
                className={`h-4 w-4 ${rotateM.isPending ? "animate-spin" : ""}`}
              />
              Rotate token
            </button>
          </div>
          {revealedToken && (
            <p className="break-all rounded-md border border-ink-200 bg-ink-50 p-3 font-mono text-xs text-ink-800">
              {revealedToken}
            </p>
          )}
        </div>
      </div>

      <div className="card overflow-hidden">
        <div className="border-b border-ink-200 px-5 py-4">
          <h2 className="flex items-center gap-2 text-base font-semibold text-ink-900">
            <Download className="h-4 w-4 text-brand-600" />
            Linux installer package
          </h2>
          <p className="mt-1 text-sm text-ink-500">
            One sealed <code className="text-xs">.run</code> file embeds the
            agent, Prompt Guard extension, and this organization’s enrollment
            secrets. Employees install once — available browsers get the managed
            extension; agents register only to your tenant.
          </p>
        </div>
        <div className="flex flex-col gap-4 p-5 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-start gap-3 text-sm text-ink-600">
            <Server className="mt-0.5 h-5 w-5 shrink-0 text-ink-400" />
            <div>
              <p>
                Ready for packaging:{" "}
                <span className="font-medium text-ink-900">
                  {data.installer_linux_ready ? "Yes" : "Partial (rebuild assets)"}
                </span>
              </p>
              <p className="mt-1 text-xs text-ink-500">
                Run <code className="text-xs">make installer-linux</code> so the
                API embeds the GUI, agent binary, and browser-extension sources.
              </p>
            </div>
          </div>
          <button
            type="button"
            className="btn-primary"
            disabled={downloadM.isPending}
            onClick={() => void handleDownload()}
          >
            <Download className="h-4 w-4" />
            {downloadM.isPending ? "Preparing…" : "Download sealed installer"}
          </button>
        </div>
      </div>

      <div className="rounded-lg border border-ink-200 bg-white px-5 py-4 text-sm text-ink-600">
        <p className="font-medium text-ink-900">Share with employees</p>
        <ol className="mt-2 list-decimal space-y-1 pl-5">
          <li>Send the single <code className="text-xs">.run</code> file (internal channel only).</li>
          <li>
            They double-click / run{" "}
            <code className="text-xs">./aispm-agent-linux-*.run</code> and enter
            their password once — install is automatic (agent + browser extension).
          </li>
          <li>
            After install, quit and reopen browsers; confirm Prompt Guard on
            chrome://extensions (and Firefox add-ons). Device appears Online under{" "}
            <a className="text-brand-700 underline" href="/agents">
              Agent Fleet
            </a>
            .
          </li>
        </ol>
      </div>
    </div>
  );
}
