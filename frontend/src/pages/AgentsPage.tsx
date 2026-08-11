import { useMemo, useState } from "react";
import {
  Archive,
  Ban,
  RefreshCw,
  Search,
  Server,
  ShieldAlert,
  Trash2,
  X,
} from "lucide-react";
import { StatusBadge } from "@/components/ui/StatusBadge";
import {
  EmptyState,
  ErrorState,
  PageHeader,
  Spinner,
} from "@/components/ui/States";
import { useAgents, useDeleteAgent, useRevokeAgent } from "@/hooks/queries";
import { ApiError } from "@/lib/api";
import { cn, formatRelative } from "@/lib/utils";
import type { AgentResponse, AgentStatus } from "@/types/api";

const FILTERS: { label: string; value: AgentStatus | "all" }[] = [
  { label: "All", value: "all" },
  { label: "Online", value: "online" },
  { label: "Offline", value: "offline" },
  { label: "Pending", value: "pending" },
  { label: "Revoked", value: "revoked" },
];

type DataChoice = "keep" | "purge";

export function AgentsPage() {
  const { data, isLoading, isError, error, refetch, isFetching } = useAgents();
  const revokeM = useRevokeAgent();
  const deleteM = useDeleteAgent();
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<AgentStatus | "all">("all");
  const [confirmRevoke, setConfirmRevoke] = useState<AgentResponse | null>(
    null,
  );
  const [confirmDelete, setConfirmDelete] = useState<AgentResponse | null>(
    null,
  );
  const [dataChoice, setDataChoice] = useState<DataChoice>("keep");
  const [revokeError, setRevokeError] = useState<string | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const agents = data ?? [];

  const filtered = useMemo(() => {
    return agents.filter((a) => {
      const matchesStatus = filter === "all" || a.status === filter;
      const matchesQuery =
        !query ||
        a.hostname.toLowerCase().includes(query.toLowerCase()) ||
        (a.agent_version ?? "").toLowerCase().includes(query.toLowerCase());
      return matchesStatus && matchesQuery;
    });
  }, [agents, filter, query]);

  const counts = useMemo(() => {
    return {
      online: agents.filter((a) => a.status === "online").length,
      total: agents.length,
    };
  }, [agents]);

  async function handleRevoke() {
    if (!confirmRevoke) return;
    setRevokeError(null);
    try {
      await revokeM.mutateAsync(confirmRevoke.id);
      setConfirmRevoke(null);
    } catch (err) {
      setRevokeError(
        err instanceof ApiError ? err.detail : "Failed to revoke agent.",
      );
    }
  }

  async function handleDelete() {
    if (!confirmDelete) return;
    setDeleteError(null);
    try {
      await deleteM.mutateAsync({
        id: confirmDelete.id,
        purge_data: dataChoice === "purge",
      });
      setConfirmDelete(null);
      setDataChoice("keep");
    } catch (err) {
      setDeleteError(
        err instanceof ApiError ? err.detail : "Failed to delete agent.",
      );
    }
  }

  function openDelete(agent: AgentResponse) {
    setDeleteError(null);
    setDataChoice("keep");
    setConfirmDelete(agent);
  }

  return (
    <>
      <PageHeader
        title="Agent Fleet"
        description={
          isLoading
            ? "Loading endpoint agents…"
            : `${counts.online} of ${counts.total} agents online`
        }
        actions={
          <button
            className="btn-ghost"
            onClick={() => refetch()}
            disabled={isFetching}
          >
            <RefreshCw
              className={cn("h-4 w-4", isFetching && "animate-spin")}
            />
            Refresh
          </button>
        }
      />

      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div className="relative w-full max-w-xs">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-400" />
          <input
            className="input pl-9"
            placeholder="Search by hostname or version…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </div>
        <div className="inline-flex rounded-lg border border-ink-200 bg-white p-1">
          {FILTERS.map((f) => (
            <button
              key={f.value}
              onClick={() => setFilter(f.value)}
              className={cn(
                "rounded-md px-3 py-1.5 text-sm font-medium transition-colors",
                filter === f.value
                  ? "bg-ink-900 text-white"
                  : "text-ink-500 hover:text-ink-900",
              )}
            >
              {f.label}
            </button>
          ))}
        </div>
      </div>

      <div className="card overflow-hidden">
        {isLoading ? (
          <Spinner label="Loading agent fleet…" />
        ) : isError ? (
          <ErrorState error={error} onRetry={() => refetch()} />
        ) : filtered.length === 0 ? (
          <EmptyState
            icon={Server}
            title={agents.length === 0 ? "No agents registered" : "No matches"}
            description={
              agents.length === 0
                ? "Deploy the AI-SPM endpoint agent to start monitoring AI activity across your fleet."
                : "Try adjusting your search or status filter."
            }
            action={
              agents.length === 0 ? (
                <a href="/agents/download" className="btn-primary">
                  Download Agent
                </a>
              ) : undefined
            }
          />
        ) : (
          <div className="scroll-thin overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-ink-200 bg-ink-50/60 text-xs uppercase tracking-wide text-ink-500">
                  <th className="px-5 py-3 font-semibold">Hostname</th>
                  <th className="px-5 py-3 font-semibold">Status</th>
                  <th className="px-5 py-3 font-semibold">OS</th>
                  <th className="px-5 py-3 font-semibold">Agent Version</th>
                  <th className="px-5 py-3 font-semibold">Last Heartbeat</th>
                  <th className="px-5 py-3 font-semibold">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-ink-100">
                {filtered.map((a) => (
                  <tr
                    key={a.id}
                    className="transition-colors hover:bg-ink-50/60"
                  >
                    <td className="px-5 py-3.5">
                      <div className="flex items-center gap-3">
                        <div className="grid h-8 w-8 place-items-center rounded-lg bg-ink-100 text-ink-500">
                          <Server className="h-4 w-4" />
                        </div>
                        <div className="min-w-0">
                          <p className="truncate font-medium text-ink-900">
                            {a.hostname}
                          </p>
                          <p className="font-mono text-xs text-ink-400">
                            {a.id.slice(0, 8)}
                          </p>
                        </div>
                      </div>
                    </td>
                    <td className="px-5 py-3.5">
                      <StatusBadge status={a.status} />
                    </td>
                    <td className="px-5 py-3.5 text-ink-600">
                      {a.os_version ?? "—"}
                    </td>
                    <td className="px-5 py-3.5">
                      <span className="font-mono text-xs text-ink-600">
                        {a.agent_version ?? "—"}
                      </span>
                    </td>
                    <td className="px-5 py-3.5 text-ink-600">
                      {formatRelative(a.last_heartbeat_at)}
                    </td>
                    <td className="px-5 py-3.5">
                      <div className="flex items-center gap-2">
                        {a.status !== "revoked" ? (
                          <button
                            className="inline-flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-xs font-medium text-rose-600 hover:bg-rose-50"
                            onClick={() => {
                              setRevokeError(null);
                              setConfirmRevoke(a);
                            }}
                          >
                            <Ban className="h-3.5 w-3.5" />
                            Revoke
                          </button>
                        ) : null}
                        <button
                          className="inline-flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-xs font-medium text-ink-600 hover:bg-ink-100"
                          onClick={() => openDelete(a)}
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                          Delete
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {confirmRevoke && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-ink-900/60 p-4 backdrop-blur-[2px]">
          <div className="w-full max-w-lg animate-fade-in overflow-hidden rounded-2xl border border-ink-200 bg-white shadow-2xl shadow-ink-900/20">
            <div className="flex items-start justify-between border-b border-ink-100 bg-gradient-to-br from-rose-50 to-white px-6 py-5">
              <div className="flex gap-3">
                <div className="grid h-11 w-11 place-items-center rounded-xl bg-rose-100 text-rose-700 ring-1 ring-rose-200">
                  <ShieldAlert className="h-5 w-5" />
                </div>
                <div>
                  <h3 className="text-lg font-semibold text-ink-900">
                    Revoke this agent?
                  </h3>
                  <p className="mt-0.5 font-mono text-xs text-ink-400">
                    {confirmRevoke.hostname} · {confirmRevoke.id.slice(0, 8)}
                  </p>
                </div>
              </div>
              <button
                type="button"
                className="rounded-lg p-1.5 text-ink-400 hover:bg-ink-100 hover:text-ink-700"
                onClick={() => {
                  setConfirmRevoke(null);
                  setRevokeError(null);
                }}
              >
                <X className="h-5 w-5" />
              </button>
            </div>
            <div className="space-y-3 px-6 py-5 text-sm leading-relaxed text-ink-600">
              <p>
                <strong className="text-ink-800">Gateway access is blocked</strong>{" "}
                for this agent ID. Heartbeats and prompt inspection are rejected.
                The agent will not automatically re-enroll under this identity.
              </p>
              <p>
                The software may still be running on the machine until IT
                uninstalls it (`aispm-agent uninstall`). Local proxy settings and
                the MITM certificate are not removed by revoke alone.
              </p>
              <p>
                Audit history for this agent is kept. To remove the fleet row
                later, use Delete.
              </p>
              {revokeError && (
                <p className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-rose-700">
                  {revokeError}
                </p>
              )}
            </div>
            <div className="flex justify-end gap-2 border-t border-ink-100 bg-ink-50/80 px-6 py-4">
              <button
                className="btn-ghost"
                onClick={() => {
                  setConfirmRevoke(null);
                  setRevokeError(null);
                }}
              >
                Cancel
              </button>
              <button
                className="btn bg-rose-600 text-white hover:bg-rose-700"
                onClick={handleRevoke}
                disabled={revokeM.isPending}
              >
                {revokeM.isPending ? "Revoking…" : "Revoke agent"}
              </button>
            </div>
          </div>
        </div>
      )}

      {confirmDelete && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-ink-900/60 p-4 backdrop-blur-[2px]">
          <div className="w-full max-w-lg animate-fade-in overflow-hidden rounded-2xl border border-ink-200 bg-white shadow-2xl shadow-ink-900/20">
            <div className="flex items-start justify-between border-b border-ink-100 bg-gradient-to-br from-ink-50 to-white px-6 py-5">
              <div className="flex gap-3">
                <div className="grid h-11 w-11 place-items-center rounded-xl bg-ink-900 text-white">
                  <Trash2 className="h-5 w-5" />
                </div>
                <div>
                  <h3 className="text-lg font-semibold text-ink-900">
                    Delete agent from fleet?
                  </h3>
                  <p className="mt-0.5 font-mono text-xs text-ink-400">
                    {confirmDelete.hostname} · {confirmDelete.id.slice(0, 8)}
                  </p>
                </div>
              </div>
              <button
                type="button"
                className="rounded-lg p-1.5 text-ink-400 hover:bg-ink-100 hover:text-ink-700"
                onClick={() => {
                  setConfirmDelete(null);
                  setDeleteError(null);
                  setDataChoice("keep");
                }}
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            <div className="space-y-4 px-6 py-5">
              <p className="text-sm leading-relaxed text-ink-600">
                Removes this endpoint from the Agent Fleet. The agent on that
                machine will stop masking within about a minute (next heartbeat)
                and will not re-enroll until you reinstall. To stop protection
                immediately, also run uninstall on the machine.
              </p>

              <p className="text-xs font-semibold uppercase tracking-wider text-ink-500">
                Audit data for this agent
              </p>
              <div className="grid gap-3">
                <label
                  className={cn(
                    "flex cursor-pointer gap-3 rounded-xl border p-4 transition-colors",
                    dataChoice === "keep"
                      ? "border-brand-500 bg-brand-50/60 ring-1 ring-brand-500/30"
                      : "border-ink-200 hover:border-ink-300 hover:bg-ink-50/80",
                  )}
                >
                  <input
                    type="radio"
                    name="agent-data"
                    className="mt-1"
                    checked={dataChoice === "keep"}
                    onChange={() => setDataChoice("keep")}
                  />
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <Archive className="h-4 w-4 text-brand-600" />
                      <span className="text-sm font-semibold text-ink-900">
                        Keep audit history
                      </span>
                    </div>
                    <p className="mt-1 text-sm leading-relaxed text-ink-500">
                      Recommended. Prompt and threat events stay in Audit Log /
                      Threat Feed for compliance, even after the fleet row is
                      removed.
                    </p>
                  </div>
                </label>

                <label
                  className={cn(
                    "flex cursor-pointer gap-3 rounded-xl border p-4 transition-colors",
                    dataChoice === "purge"
                      ? "border-rose-400 bg-rose-50/70 ring-1 ring-rose-400/30"
                      : "border-ink-200 hover:border-ink-300 hover:bg-ink-50/80",
                  )}
                >
                  <input
                    type="radio"
                    name="agent-data"
                    className="mt-1"
                    checked={dataChoice === "purge"}
                    onChange={() => setDataChoice("purge")}
                  />
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <Trash2 className="h-4 w-4 text-rose-600" />
                      <span className="text-sm font-semibold text-ink-900">
                        Delete audit data as well
                      </span>
                    </div>
                    <p className="mt-1 text-sm leading-relaxed text-ink-500">
                      Permanently removes audit events attributed to this agent.
                      This cannot be undone.
                    </p>
                  </div>
                </label>
              </div>

              {deleteError && (
                <p className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">
                  {deleteError}
                </p>
              )}
            </div>

            <div className="flex justify-end gap-2 border-t border-ink-100 bg-ink-50/80 px-6 py-4">
              <button
                className="btn-ghost"
                onClick={() => {
                  setConfirmDelete(null);
                  setDeleteError(null);
                  setDataChoice("keep");
                }}
              >
                Cancel
              </button>
              <button
                className={cn(
                  "btn text-white",
                  dataChoice === "purge"
                    ? "bg-rose-600 hover:bg-rose-700"
                    : "bg-ink-900 hover:bg-ink-800",
                )}
                onClick={handleDelete}
                disabled={deleteM.isPending}
              >
                {deleteM.isPending
                  ? "Deleting…"
                  : dataChoice === "purge"
                    ? "Delete agent & data"
                    : "Delete agent, keep data"}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
