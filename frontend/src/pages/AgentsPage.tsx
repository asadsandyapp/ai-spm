import { useMemo, useState } from "react";
import { Ban, RefreshCw, Search, Server, Trash2 } from "lucide-react";
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
      await deleteM.mutateAsync(confirmDelete.id);
      setConfirmDelete(null);
    } catch (err) {
      setDeleteError(
        err instanceof ApiError ? err.detail : "Failed to delete agent.",
      );
    }
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
                            onClick={() => setConfirmRevoke(a)}
                          >
                            <Ban className="h-3.5 w-3.5" />
                            Revoke
                          </button>
                        ) : null}
                        <button
                          className="inline-flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-xs font-medium text-ink-600 hover:bg-ink-100"
                          onClick={() => setConfirmDelete(a)}
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
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-ink-900/50 p-4">
          <div className="card w-full max-w-md p-5">
            <h3 className="text-lg font-semibold text-ink-900">
              Revoke agent?
            </h3>
            <p className="mt-2 text-sm text-ink-500">
              This will immediately disconnect{" "}
              <strong>{confirmRevoke.hostname}</strong> and block future
              connections. The agent cannot be re-activated without re-enrollment.
            </p>
            {revokeError && (
              <p className="mt-2 text-sm text-rose-600">{revokeError}</p>
            )}
            <div className="mt-5 flex justify-end gap-2">
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
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-ink-900/50 p-4">
          <div className="card w-full max-w-md p-5">
            <h3 className="text-lg font-semibold text-ink-900">
              Delete agent?
            </h3>
            <p className="mt-2 text-sm text-ink-500">
              This permanently removes{" "}
              <strong>{confirmDelete.hostname}</strong> (
              {confirmDelete.id.slice(0, 8)}) from the fleet list.
              {confirmDelete.status !== "revoked" ? (
                <>
                  {" "}
                  The agent will be disconnected immediately and must re-enroll
                  to appear again.
                </>
              ) : (
                <> Historical audit events for this agent are kept.</>
              )}
            </p>
            {deleteError && (
              <p className="mt-2 text-sm text-rose-600">{deleteError}</p>
            )}
            <div className="mt-5 flex justify-end gap-2">
              <button
                className="btn-ghost"
                onClick={() => {
                  setConfirmDelete(null);
                  setDeleteError(null);
                }}
              >
                Cancel
              </button>
              <button
                className="btn bg-rose-600 text-white hover:bg-rose-700"
                onClick={handleDelete}
                disabled={deleteM.isPending}
              >
                {deleteM.isPending ? "Deleting…" : "Delete agent"}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
