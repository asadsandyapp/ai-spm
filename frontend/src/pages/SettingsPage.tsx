import { useState } from "react";
import { Bot, KeyRound, Plus, Users, X } from "lucide-react";
import { StatusBadge } from "@/components/ui/StatusBadge";
import {
  EmptyState,
  ErrorState,
  PageHeader,
  Spinner,
} from "@/components/ui/States";
import {
  useCreateUser,
  useLlmConfigs,
  useUpsertLlmConfig,
  useUsers,
} from "@/hooks/queries";
import { ApiError } from "@/lib/api";
import { titleCase } from "@/lib/utils";
import type { UserRole } from "@/types/api";

const ROLES: UserRole[] = [
  "security_admin",
  "auditor",
  "viewer",
];

function CreateUserModal({ onClose }: { onClose: () => void }) {
  const createM = useCreateUser();
  const [email, setEmail] = useState("");
  const [fullName, setFullName] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<UserRole>("viewer");
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await createM.mutateAsync({ email, full_name: fullName, password, role });
      onClose();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Failed to create user.");
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-ink-900/50 p-4">
      <div className="card w-full max-w-md animate-fade-in">
        <div className="flex items-center justify-between border-b border-ink-200 px-5 py-4">
          <h2 className="text-lg font-semibold text-ink-900">Invite User</h2>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md p-1.5 text-ink-400 hover:bg-ink-100"
          >
            <X className="h-5 w-5" />
          </button>
        </div>
        <form onSubmit={handleSubmit} className="space-y-4 p-5">
          <div>
            <label className="label" htmlFor="user-email">
              Email
            </label>
            <input
              id="user-email"
              type="email"
              className="input"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
            />
          </div>
          <div>
            <label className="label" htmlFor="user-name">
              Full name
            </label>
            <input
              id="user-name"
              className="input"
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              required
              minLength={2}
            />
          </div>
          <div>
            <label className="label" htmlFor="user-password">
              Temporary password
            </label>
            <input
              id="user-password"
              type="password"
              className="input"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              minLength={12}
            />
            <p className="mt-1 text-xs text-ink-400">Minimum 12 characters</p>
          </div>
          <div>
            <label className="label" htmlFor="user-role">
              Role
            </label>
            <select
              id="user-role"
              className="input"
              value={role}
              onChange={(e) => setRole(e.target.value as UserRole)}
            >
              {ROLES.map((r) => (
                <option key={r} value={r}>
                  {titleCase(r)}
                </option>
              ))}
            </select>
          </div>
          {error && (
            <p className="text-sm text-rose-600" role="alert">
              {error}
            </p>
          )}
          <div className="flex justify-end gap-2 pt-2">
            <button type="button" className="btn-ghost" onClick={onClose}>
              Cancel
            </button>
            <button
              type="submit"
              className="btn-primary"
              disabled={createM.isPending}
            >
              {createM.isPending ? "Creating…" : "Create user"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

function LlmConfigSection() {
  const { data, isLoading, isError, error, refetch } = useLlmConfigs();
  const upsertM = useUpsertLlmConfig();
  const configs = data ?? [];

  const [provider, setProvider] = useState("openai");
  const [apiKey, setApiKey] = useState("");
  const [isActive, setIsActive] = useState(true);
  const [formError, setFormError] = useState<string | null>(null);

  async function handleUpsert(e: React.FormEvent) {
    e.preventDefault();
    setFormError(null);
    try {
      await upsertM.mutateAsync({ provider, api_key: apiKey, is_active: isActive });
      setApiKey("");
    } catch (err) {
      setFormError(
        err instanceof ApiError ? err.detail : "Failed to save LLM config.",
      );
    }
  }

  return (
    <section className="card p-5">
      <div className="mb-4 flex items-center gap-3">
        <div className="grid h-10 w-10 place-items-center rounded-lg bg-violet-50 text-violet-600">
          <Bot className="h-5 w-5" />
        </div>
        <div>
          <h2 className="text-sm font-semibold text-ink-900">LLM Provider</h2>
          <p className="text-xs text-ink-500">
            Configure the LLM backend used for policy-assisted responses.
          </p>
        </div>
      </div>

      {isLoading ? (
        <Spinner label="Loading LLM configs…" />
      ) : isError ? (
        <ErrorState error={error} onRetry={() => refetch()} />
      ) : (
        <>
          {configs.length > 0 ? (
            <ul className="mb-5 divide-y divide-ink-100 rounded-lg border border-ink-200">
              {configs.map((c) => (
                <li
                  key={c.id}
                  className="flex items-center justify-between px-4 py-3"
                >
                  <div>
                    <p className="font-medium text-ink-900">
                      {titleCase(c.provider)}
                    </p>
                    <p className="font-mono text-xs text-ink-400">
                      {c.id.slice(0, 8)}
                    </p>
                  </div>
                  <StatusBadge status={c.is_active ? "active" : "inactive"} />
                </li>
              ))}
            </ul>
          ) : (
            <p className="mb-5 text-sm text-ink-500">
              No LLM provider configured yet.
            </p>
          )}

          <form onSubmit={handleUpsert} className="space-y-4">
            <div>
              <label className="label" htmlFor="llm-provider">
                Provider
              </label>
              <select
                id="llm-provider"
                className="input"
                value={provider}
                onChange={(e) => setProvider(e.target.value)}
              >
                <option value="openai">OpenAI</option>
                <option value="anthropic">Anthropic</option>
                <option value="azure">Azure OpenAI</option>
              </select>
            </div>
            <div>
              <label className="label" htmlFor="llm-key">
                API Key
              </label>
              <div className="relative">
                <KeyRound className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-400" />
                <input
                  id="llm-key"
                  type="password"
                  className="input pl-9 font-mono text-xs"
                  value={apiKey}
                  onChange={(e) => setApiKey(e.target.value)}
                  placeholder="sk-…"
                  required
                  minLength={10}
                />
              </div>
            </div>
            <label className="flex items-center gap-2 text-sm text-ink-700">
              <input
                type="checkbox"
                checked={isActive}
                onChange={(e) => setIsActive(e.target.checked)}
                className="rounded border-ink-300"
              />
              Active
            </label>
            {formError && (
              <p className="text-sm text-rose-600" role="alert">
                {formError}
              </p>
            )}
            <button
              type="submit"
              className="btn-primary"
              disabled={upsertM.isPending}
            >
              {upsertM.isPending ? "Saving…" : "Save configuration"}
            </button>
          </form>
        </>
      )}
    </section>
  );
}

export function SettingsPage() {
  const { data, isLoading, isError, error, refetch } = useUsers();
  const users = data ?? [];
  const [showCreate, setShowCreate] = useState(false);

  return (
    <>
      <PageHeader
        title="Settings"
        description="Manage organization users and LLM provider configuration."
      />

      <div className="grid gap-6 lg:grid-cols-2">
        <section className="card overflow-hidden">
          <div className="flex items-center justify-between border-b border-ink-200 px-5 py-4">
            <div className="flex items-center gap-3">
              <div className="grid h-10 w-10 place-items-center rounded-lg bg-brand-50 text-brand-600">
                <Users className="h-5 w-5" />
              </div>
              <div>
                <h2 className="text-sm font-semibold text-ink-900">Users</h2>
                <p className="text-xs text-ink-500">
                  {users.length} team member{users.length === 1 ? "" : "s"}
                </p>
              </div>
            </div>
            <button
              className="btn-primary py-2"
              onClick={() => setShowCreate(true)}
            >
              <Plus className="h-4 w-4" />
              Invite
            </button>
          </div>

          {isLoading ? (
            <Spinner label="Loading users…" />
          ) : isError ? (
            <ErrorState error={error} onRetry={() => refetch()} />
          ) : users.length === 0 ? (
            <EmptyState
              icon={Users}
              title="No users"
              description="Invite team members to collaborate on security operations."
            />
          ) : (
            <div className="scroll-thin overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead>
                  <tr className="border-b border-ink-200 bg-ink-50/60 text-xs uppercase tracking-wide text-ink-500">
                    <th className="px-5 py-3 font-semibold">Name</th>
                    <th className="px-5 py-3 font-semibold">Email</th>
                    <th className="px-5 py-3 font-semibold">Role</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-ink-100">
                  {users.map((u) => (
                    <tr
                      key={u.id}
                      className="transition-colors hover:bg-ink-50/60"
                    >
                      <td className="px-5 py-3.5 font-medium text-ink-900">
                        {u.full_name}
                      </td>
                      <td className="px-5 py-3.5 text-ink-600">{u.email}</td>
                      <td className="px-5 py-3.5">
                        <StatusBadge status={u.role} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>

        <LlmConfigSection />
      </div>

      {showCreate && <CreateUserModal onClose={() => setShowCreate(false)} />}
    </>
  );
}
