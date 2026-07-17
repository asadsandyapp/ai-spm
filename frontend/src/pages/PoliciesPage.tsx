import { useCallback, useState } from "react";
import { Pencil, Plus, ScrollText, Star, Trash2, X } from "lucide-react";
import { StatusBadge } from "@/components/ui/StatusBadge";
import {
  EmptyState,
  ErrorState,
  PageHeader,
  Spinner,
} from "@/components/ui/States";
import {
  useCreatePolicy,
  useDeletePolicy,
  usePolicies,
  useUpdatePolicy,
} from "@/hooks/queries";
import { ApiError } from "@/lib/api";
import type { PolicyResponse } from "@/types/api";

const DEFAULT_RULES = '{\n  "rules": []\n}';

function ruleCount(rules: Record<string, unknown>): number {
  if (!rules || typeof rules !== "object") return 0;
  const value = Object.values(rules).find((v) => Array.isArray(v));
  if (Array.isArray(value)) return value.length;
  return Object.keys(rules).length;
}

interface PolicyFormState {
  name: string;
  description: string;
  rulesJson: string;
  is_default: boolean;
  is_active: boolean;
}

function emptyForm(): PolicyFormState {
  return {
    name: "",
    description: "",
    rulesJson: DEFAULT_RULES,
    is_default: false,
    is_active: true,
  };
}

function formFromPolicy(p: PolicyResponse): PolicyFormState {
  return {
    name: p.name,
    description: p.description ?? "",
    rulesJson: JSON.stringify(p.rules, null, 2),
    is_default: p.is_default,
    is_active: p.is_active,
  };
}

function PolicyModal({
  mode,
  policy,
  onClose,
}: {
  mode: "create" | "edit";
  policy?: PolicyResponse;
  onClose: () => void;
}) {
  const createM = useCreatePolicy();
  const updateM = useUpdatePolicy();
  const [form, setForm] = useState<PolicyFormState>(
    policy ? formFromPolicy(policy) : emptyForm(),
  );
  const [error, setError] = useState<string | null>(null);

  const saving = createM.isPending || updateM.isPending;

  const handleSubmit = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      setError(null);

      let rules: Record<string, unknown>;
      try {
        rules = JSON.parse(form.rulesJson) as Record<string, unknown>;
      } catch {
        setError("Rules must be valid JSON.");
        return;
      }

      try {
        if (mode === "create") {
          await createM.mutateAsync({
            name: form.name.trim(),
            description: form.description.trim() || null,
            rules,
            is_default: form.is_default,
          });
        } else if (policy) {
          await updateM.mutateAsync({
            id: policy.id,
            body: {
              name: form.name.trim(),
              description: form.description.trim() || null,
              rules,
              is_active: form.is_active,
            },
          });
        }
        onClose();
      } catch (err) {
        setError(err instanceof ApiError ? err.detail : "Failed to save policy.");
      }
    },
    [createM, updateM, form, mode, onClose, policy],
  );

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-ink-900/50 p-4">
      <div
        className="card w-full max-w-lg animate-fade-in"
        role="dialog"
        aria-modal="true"
        aria-labelledby="policy-modal-title"
      >
        <div className="flex items-center justify-between border-b border-ink-200 px-5 py-4">
          <h2 id="policy-modal-title" className="text-lg font-semibold text-ink-900">
            {mode === "create" ? "Create Policy" : "Edit Policy"}
          </h2>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md p-1.5 text-ink-400 hover:bg-ink-100 hover:text-ink-700"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4 p-5">
          <div>
            <label className="label" htmlFor="policy-name">
              Name
            </label>
            <input
              id="policy-name"
              className="input"
              value={form.name}
              onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
              required
              minLength={2}
            />
          </div>

          <div>
            <label className="label" htmlFor="policy-desc">
              Description
            </label>
            <input
              id="policy-desc"
              className="input"
              value={form.description}
              onChange={(e) =>
                setForm((f) => ({ ...f, description: e.target.value }))
              }
            />
          </div>

          <div>
            <label className="label" htmlFor="policy-rules">
              Rules (JSON)
            </label>
            <textarea
              id="policy-rules"
              className="input min-h-[160px] font-mono text-xs"
              value={form.rulesJson}
              onChange={(e) =>
                setForm((f) => ({ ...f, rulesJson: e.target.value }))
              }
              spellCheck={false}
            />
          </div>

          {mode === "create" ? (
            <label className="flex items-center gap-2 text-sm text-ink-700">
              <input
                type="checkbox"
                checked={form.is_default}
                onChange={(e) =>
                  setForm((f) => ({ ...f, is_default: e.target.checked }))
                }
                className="rounded border-ink-300"
              />
              Set as default policy
            </label>
          ) : (
            <label className="flex items-center gap-2 text-sm text-ink-700">
              <input
                type="checkbox"
                checked={form.is_active}
                onChange={(e) =>
                  setForm((f) => ({ ...f, is_active: e.target.checked }))
                }
                className="rounded border-ink-300"
              />
              Policy active
            </label>
          )}

          {error && (
            <p className="text-sm text-rose-600" role="alert">
              {error}
            </p>
          )}

          <div className="flex justify-end gap-2 pt-2">
            <button type="button" className="btn-ghost" onClick={onClose}>
              Cancel
            </button>
            <button type="submit" className="btn-primary" disabled={saving}>
              {saving ? "Saving…" : mode === "create" ? "Create" : "Save changes"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

export function PoliciesPage() {
  const { data, isLoading, isError, error, refetch } = usePolicies();
  const deleteM = useDeletePolicy();
  const policies = data ?? [];

  const [modal, setModal] = useState<
    { mode: "create" } | { mode: "edit"; policy: PolicyResponse } | null
  >(null);
  const [confirmDelete, setConfirmDelete] = useState<PolicyResponse | null>(
    null,
  );
  const [deleteError, setDeleteError] = useState<string | null>(null);

  async function handleDelete() {
    if (!confirmDelete) return;
    setDeleteError(null);
    try {
      await deleteM.mutateAsync(confirmDelete.id);
      setConfirmDelete(null);
    } catch (err) {
      setDeleteError(
        err instanceof ApiError ? err.detail : "Failed to delete policy.",
      );
    }
  }

  return (
    <>
      <PageHeader
        title="Policies"
        description="Detection and enforcement rules applied to every AI prompt in your organization."
        actions={
          <button
            className="btn-primary"
            onClick={() => setModal({ mode: "create" })}
          >
            <Plus className="h-4 w-4" />
            New Policy
          </button>
        }
      />

      {isLoading ? (
        <div className="card">
          <Spinner label="Loading policies…" />
        </div>
      ) : isError ? (
        <div className="card">
          <ErrorState error={error} onRetry={() => refetch()} />
        </div>
      ) : policies.length === 0 ? (
        <div className="card">
          <EmptyState
            icon={ScrollText}
            title="No policies configured"
            description="Create a policy to tailor detection and enforcement rules for your organization."
          />
        </div>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {policies.map((p) => (
            <article
              key={p.id}
              className="card flex flex-col p-5 transition-shadow hover:shadow-elevated"
            >
              <div className="flex items-start justify-between gap-3">
                <div className="grid h-10 w-10 place-items-center rounded-lg bg-brand-50 text-brand-600">
                  <ScrollText className="h-5 w-5" />
                </div>
                <StatusBadge status={p.is_active ? "active" : "inactive"} />
              </div>

              <div className="mt-4 flex-1">
                <div className="flex items-center gap-1.5">
                  <h3 className="font-semibold text-ink-900">{p.name}</h3>
                  {p.is_default && (
                    <span title="Default policy">
                      <Star className="h-3.5 w-3.5 fill-amber-400 text-amber-400" />
                    </span>
                  )}
                </div>
                <p className="mt-1.5 line-clamp-2 text-sm text-ink-500">
                  {p.description || "No description provided."}
                </p>
              </div>

              <div className="mt-4 flex items-center justify-between border-t border-ink-100 pt-3 text-xs text-ink-500">
                <span className="font-medium">
                  {ruleCount(p.rules)} rule
                  {ruleCount(p.rules) === 1 ? "" : "s"}
                </span>
                <div className="flex items-center gap-1">
                  <button
                    className="rounded-md p-1.5 text-ink-400 hover:bg-ink-100 hover:text-brand-600"
                    title="Edit policy"
                    onClick={() => setModal({ mode: "edit", policy: p })}
                  >
                    <Pencil className="h-3.5 w-3.5" />
                  </button>
                  {!p.is_default && (
                    <button
                      className="rounded-md p-1.5 text-ink-400 hover:bg-rose-50 hover:text-rose-600"
                      title="Delete policy"
                      onClick={() => setConfirmDelete(p)}
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  )}
                </div>
              </div>
            </article>
          ))}
        </div>
      )}

      {modal && (
        <PolicyModal
          mode={modal.mode}
          policy={modal.mode === "edit" ? modal.policy : undefined}
          onClose={() => setModal(null)}
        />
      )}

      {confirmDelete && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-ink-900/50 p-4">
          <div className="card w-full max-w-md p-5">
            <h3 className="text-lg font-semibold text-ink-900">
              Delete policy?
            </h3>
            <p className="mt-2 text-sm text-ink-500">
              This will permanently remove <strong>{confirmDelete.name}</strong>.
              This action cannot be undone.
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
                {deleteM.isPending ? "Deleting…" : "Delete"}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
