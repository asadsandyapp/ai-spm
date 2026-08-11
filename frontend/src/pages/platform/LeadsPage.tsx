import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Inbox, RefreshCw } from "lucide-react";
import { StatusBadge } from "@/components/ui/StatusBadge";
import {
  EmptyState,
  ErrorState,
  PageHeader,
  Spinner,
} from "@/components/ui/States";
import { platformApi, ApiError } from "@/lib/api";
import { formatDateTime } from "@/lib/utils";

export function LeadsPage() {
  const queryClient = useQueryClient();
  const leadsQ = useQuery({
    queryKey: ["platform", "leads"],
    queryFn: ({ signal }) => platformApi.leads(signal),
  });

  const updateM = useMutation({
    mutationFn: ({ id, status }: { id: string; status: string }) =>
      platformApi.updateLead(id, { status }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["platform", "leads"] }),
  });

  const leads = leadsQ.data ?? [];

  return (
    <div className="animate-fade-in">
      <PageHeader
        title="Sales leads"
        description="Enterprise contact-sales inbox. No tenant audit content is exposed here."
        actions={
          <button
            type="button"
            className="btn-ghost"
            onClick={() => leadsQ.refetch()}
            disabled={leadsQ.isFetching}
          >
            <RefreshCw className={`h-4 w-4 ${leadsQ.isFetching ? "animate-spin" : ""}`} />
            Refresh
          </button>
        }
      />

      {leadsQ.isLoading && <Spinner />}
      {leadsQ.isError && (
        <ErrorState
          error={
            leadsQ.error instanceof ApiError
              ? leadsQ.error
              : new Error("Failed to load leads")
          }
          onRetry={() => leadsQ.refetch()}
        />
      )}

      {!leadsQ.isLoading && !leadsQ.isError && leads.length === 0 && (
        <EmptyState
          icon={Inbox}
          title="No leads yet"
          description="When prospects submit Contact sales, they appear here."
        />
      )}

      {leads.length > 0 && (
        <div className="card mt-6 overflow-hidden">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-ink-200 bg-ink-50 text-xs uppercase tracking-wide text-ink-500">
              <tr>
                <th className="px-4 py-3 font-medium">Company</th>
                <th className="px-4 py-3 font-medium">Contact</th>
                <th className="px-4 py-3 font-medium">Agents</th>
                <th className="px-4 py-3 font-medium">Status</th>
                <th className="px-4 py-3 font-medium">Created</th>
                <th className="px-4 py-3 font-medium">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-ink-100">
              {leads.map((lead) => (
                <tr key={lead.id} className="align-top">
                  <td className="px-4 py-3">
                    <p className="font-medium text-ink-900">{lead.company_name}</p>
                    {lead.message && (
                      <p className="mt-1 line-clamp-2 text-xs text-ink-500">{lead.message}</p>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    <p className="text-ink-800">{lead.contact_name ?? "—"}</p>
                    <p className="text-xs text-ink-500">
                      {lead.contact_email ?? lead.email ?? "—"}
                    </p>
                    {lead.phone && <p className="text-xs text-ink-500">{lead.phone}</p>}
                  </td>
                  <td className="px-4 py-3 text-ink-700">
                    {lead.estimated_agents ?? lead.estimated_seats ?? "—"}
                  </td>
                  <td className="px-4 py-3">
                    <StatusBadge status={lead.status} />
                  </td>
                  <td className="px-4 py-3 text-ink-500">
                    {formatDateTime(lead.created_at)}
                  </td>
                  <td className="px-4 py-3">
                    <select
                      className="input max-w-[140px] py-1.5 text-xs"
                      value={lead.status}
                      disabled={updateM.isPending}
                      onChange={(e) =>
                        updateM.mutate({ id: lead.id, status: e.target.value })
                      }
                    >
                      <option value="new">new</option>
                      <option value="contacted">contacted</option>
                      <option value="won">won</option>
                      <option value="lost">lost</option>
                    </select>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
