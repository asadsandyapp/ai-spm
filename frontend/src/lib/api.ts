import { getAuthToken, useAuthStore } from "@/stores/auth";
import type {
  AgentResponse,
  AuditEventResponse,
  AuditExportResponse,
  CreatePolicyRequest,
  CreateUserRequest,
  DashboardMetricsResponse,
  EnrollmentInfoResponse,
  LLMConfigRequest,
  LLMConfigResponse,
  LoginRequest,
  OrgTokenRotateResponse,
  PiiDetectionPolicy,
  PlatformUserResponse,
  PolicyResponse,
  ReportQuery,
  ReportSummaryResponse,
  TenantDetailResponse,
  TenantListItem,
  ThreatEventResponse,
  TokenResponse,
  UpdatePiiDetectionRequest,
  UpdatePolicyRequest,
  UsageResponse,
  UserResponse,
} from "@/types/api";

export const API_URL: string =
  (import.meta.env.VITE_API_URL as string | undefined)?.trim().replace(/\/$/, "") ??
  "http://localhost:8090";

/** Absolute API origin — empty VITE_API_URL uses the page origin (Vite proxy). */
export function apiBaseUrl(): string {
  if (API_URL) return API_URL;
  if (typeof window !== "undefined") return window.location.origin;
  return "http://localhost:8090";
}

export class ApiError extends Error {
  status: number;
  detail: string;

  constructor(status: number, detail: string) {
    super(detail);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

interface RequestOptions {
  method?: string;
  body?: unknown;
  auth?: boolean;
  query?: Record<string, string | number | undefined>;
  signal?: AbortSignal;
}

async function request<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const { method = "GET", body, auth = true, query, signal } = opts;

  // Empty VITE_API_URL + Vite dev proxy → same-origin requests (no CORS issues).
  const url = new URL(path.startsWith("/") ? path : `/${path}`, apiBaseUrl());
  if (query) {
    for (const [key, value] of Object.entries(query)) {
      if (value !== undefined) url.searchParams.set(key, String(value));
    }
  }

  const headers: Record<string, string> = { Accept: "application/json" };
  if (body !== undefined) headers["Content-Type"] = "application/json";

  if (auth) {
    const token = getAuthToken();
    if (token) headers["Authorization"] = `Bearer ${token}`;
  }

  let res: Response;
  try {
    res = await fetch(url.toString(), {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
      signal,
    });
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") throw err;
    throw new ApiError(0, "Network error — unable to reach the AI-SPM API.");
  }

  if (auth && (res.status === 401 || (res.status === 404 && path.includes("/auth/me")))) {
    // Expired/invalid token, or DB was reset while the browser kept an old JWT.
    useAuthStore.getState().logout();
  }

  if (!res.ok) {
    let detail = `Request failed with status ${res.status}`;
    try {
      const data = await res.json();
      if (typeof data?.detail === "string") {
        detail = data.detail;
      } else if (Array.isArray(data?.detail) && data.detail.length > 0) {
        const first = data.detail[0] as {
          msg?: string;
          loc?: Array<string | number>;
        };
        const field =
          Array.isArray(first.loc) && first.loc.length > 1
            ? String(first.loc[first.loc.length - 1]).replace(/_/g, " ")
            : null;
        const msg = first.msg ?? "Validation error";
        detail = field ? `${field}: ${msg}` : msg;
      }
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(res.status, detail);
  }

  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

// --- Admin (tenant) API --------------------------------------------------
export const adminApi = {
  login: (body: LoginRequest) =>
    request<TokenResponse>("/admin/v1/auth/login", {
      method: "POST",
      body,
      auth: false,
    }),
  me: (signal?: AbortSignal) =>
    request<UserResponse>("/admin/v1/auth/me", { signal }),
  updateProfile: (body: { full_name: string; email?: string }) =>
    request<UserResponse>("/admin/v1/auth/me", {
      method: "PATCH",
      body,
    }),
  changePassword: (body: { current_password: string; new_password: string }) =>
    request<{ status: string; message: string }>("/admin/v1/auth/change-password", {
      method: "POST",
      body,
    }),
  agents: (signal?: AbortSignal) =>
    request<AgentResponse[]>("/admin/v1/agents", { signal }),
  audit: (params?: { limit?: number; offset?: number }, signal?: AbortSignal) =>
    request<AuditEventResponse[]>("/admin/v1/audit", {
      query: { limit: params?.limit, offset: params?.offset },
      signal,
    }),
  policies: (signal?: AbortSignal) =>
    request<PolicyResponse[]>("/admin/v1/policies", { signal }),
  piiDetections: (signal?: AbortSignal) =>
    request<PiiDetectionPolicy[]>("/admin/v1/pii-detections", { signal }),
  updatePiiDetection: (id: string, body: UpdatePiiDetectionRequest) =>
    request<PiiDetectionPolicy>(`/admin/v1/pii-detections/${id}`, {
      method: "PUT",
      body,
    }),
  dashboardMetrics: (signal?: AbortSignal) =>
    request<DashboardMetricsResponse>("/admin/v1/dashboard/metrics", { signal }),
  reportSummary: (params: ReportQuery = {}, signal?: AbortSignal) =>
    request<ReportSummaryResponse>("/admin/v1/reports/summary", {
      query: {
        days: params.days,
        event_type: params.event_type,
        provider: params.provider,
        device: params.device,
        entity: params.entity,
      },
      signal,
    }),
  dashboardThreats: (limit = 50, signal?: AbortSignal) =>
    request<ThreatEventResponse[]>("/admin/v1/dashboard/threats", {
      query: { limit },
      signal,
    }),
  createPolicy: (body: CreatePolicyRequest) =>
    request<PolicyResponse>("/admin/v1/policies", { method: "POST", body }),
  updatePolicy: (id: string, body: UpdatePolicyRequest) =>
    request<PolicyResponse>(`/admin/v1/policies/${id}`, {
      method: "PUT",
      body,
    }),
  deletePolicy: (id: string) =>
    request<void>(`/admin/v1/policies/${id}`, { method: "DELETE" }),
  revokeAgent: (id: string) =>
    request<{ status: string; agent_id: string }>(
      `/admin/v1/agents/${id}/revoke`,
      { method: "POST" },
    ),
  deleteAgent: (id: string, opts?: { purge_data?: boolean }) =>
    request<void>(`/admin/v1/agents/${id}`, {
      method: "DELETE",
      query: opts?.purge_data ? { purge_data: "true" } : undefined,
    }),
  enrollment: (signal?: AbortSignal) =>
    request<EnrollmentInfoResponse>("/admin/v1/agents/enrollment", { signal }),
  rotateOrgToken: () =>
    request<OrgTokenRotateResponse>("/admin/v1/org-token/rotate", {
      method: "POST",
    }),
  downloadLinuxInstaller: async (): Promise<{
    blob: Blob;
    orgToken: string | null;
    filename: string;
  }> => {
    const url = new URL("/admin/v1/agents/installer/linux", apiBaseUrl());
    const token = getAuthToken();
    const headers: Record<string, string> = {
      Accept: "application/x-makeself, application/octet-stream",
    };
    if (token) headers["Authorization"] = `Bearer ${token}`;

    const res = await fetch(url.toString(), { headers });
    if (res.status === 401) {
      useAuthStore.getState().logout();
    }
    if (!res.ok) {
      let detail = `Installer download failed with status ${res.status}`;
      try {
        const data = await res.json();
        if (typeof data?.detail === "string") detail = data.detail;
      } catch {
        /* non-JSON */
      }
      throw new ApiError(res.status, detail);
    }
    const disposition = res.headers.get("Content-Disposition") || "";
    const match = /filename="?([^";]+)"?/i.exec(disposition);
    const filename = match?.[1] ?? "aispm-agent-linux.run";
    const orgToken = res.headers.get("X-AISPM-Org-Token");
    return { blob: await res.blob(), orgToken, filename };
  },
  exportAudit: (days = 90) =>
    request<AuditExportResponse>("/admin/v1/audit/export", {
      method: "POST",
      query: { days },
    }),
  downloadAuditExport: async (days = 90): Promise<Blob> => {
    const url = new URL("/admin/v1/audit/export/download", apiBaseUrl());
    url.searchParams.set("days", String(days));
    const token = getAuthToken();
    const headers: Record<string, string> = { Accept: "text/csv" };
    if (token) headers["Authorization"] = `Bearer ${token}`;

    const res = await fetch(url.toString(), { headers });
    if (!res.ok) {
      let detail = `Export download failed with status ${res.status}`;
      try {
        const data = await res.json();
        if (typeof data?.detail === "string") detail = data.detail;
      } catch {
        /* non-JSON */
      }
      throw new ApiError(res.status, detail);
    }
    return res.blob();
  },
  users: (signal?: AbortSignal) =>
    request<UserResponse[]>("/admin/v1/users", { signal }),
  createUser: (body: CreateUserRequest) =>
    request<UserResponse>("/admin/v1/users", { method: "POST", body }),
  llmConfigs: (signal?: AbortSignal) =>
    request<LLMConfigResponse[]>("/admin/v1/llm-configs", { signal }),
  upsertLlmConfig: (body: LLMConfigRequest) =>
    request<LLMConfigResponse>("/admin/v1/llm-configs", {
      method: "POST",
      body,
    }),
  billingStatus: async (signal?: AbortSignal) => {
    type BillingStatus = {
      org_id: string;
      plan: string;
      status: string;
      onboarding_step: string;
      console_access: boolean;
      entitlements: Record<string, unknown>;
      usage: {
        agent_count: number;
        prompts_today: number;
        prompts_this_month: number;
        max_agents: number;
        max_prompts_per_day: number;
        max_prompts_per_month: number;
        plan: string;
        status?: string;
        max_agents_unlimited?: boolean;
        prompts_unlimited?: boolean;
      };
    };
    try {
      return await request<BillingStatus>("/admin/v1/billing/status", { signal });
    } catch (err) {
      // Docker API image exposes /subscription + /usage instead of /status.
      if (!(err instanceof ApiError) || err.status !== 404) throw err;
      const [sub, usage] = await Promise.all([
        request<{
          plan: string;
          status: string;
          max_agents: number | null;
          max_prompts_per_day: number;
          entitlements: Record<string, unknown>;
          current_period_end?: string | null;
        }>("/admin/v1/billing/subscription", { signal }),
        request<{
          agent_count: number;
          prompts_today: number;
          max_agents: number | null;
          max_prompts_per_day: number;
          plan: string;
          status?: string;
        }>("/admin/v1/billing/usage", { signal }),
      ]);
      const consoleAccess = ["active", "past_due"].includes(sub.status);
      const maxAgents = sub.max_agents ?? usage.max_agents ?? 0;
      const maxPrompts = sub.max_prompts_per_day ?? usage.max_prompts_per_day ?? 0;
      const agentsUnlimited = sub.max_agents == null || sub.max_agents < 0;
      const promptsUnlimited = maxPrompts < 0;
      return {
        org_id: "",
        plan: sub.plan,
        status: sub.status,
        onboarding_step: consoleAccess ? "complete" : "select_plan",
        console_access: consoleAccess,
        entitlements: {
          ...sub.entitlements,
          console_access: consoleAccess,
          current_period_end: sub.current_period_end ?? null,
          max_agents_unlimited: agentsUnlimited,
        },
        usage: {
          agent_count: usage.agent_count,
          prompts_today: usage.prompts_today,
          prompts_this_month: usage.prompts_today,
          max_agents: typeof maxAgents === "number" ? maxAgents : 0,
          max_prompts_per_day: maxPrompts,
          max_prompts_per_month: maxPrompts,
          plan: usage.plan || sub.plan,
          status: usage.status ?? sub.status,
          max_agents_unlimited: agentsUnlimited,
          prompts_unlimited: promptsUnlimited,
        },
      } satisfies BillingStatus;
    }
  },
  selectPlan: (body: { plan: string }) =>
    request<Record<string, unknown>>("/admin/v1/billing/select-plan", {
      method: "POST",
      body,
    }),
  checkout: (body: {
    plan: string;
    success_url?: string;
    cancel_url?: string;
  }) =>
    request<{
      mode: string;
      checkout_url?: string;
      session_id?: string | null;
      message?: string;
    }>("/admin/v1/billing/checkout", {
      method: "POST",
      body,
    }),
  devActivate: (body: { plan: string }) =>
    request<{
      console_access: boolean;
      plan: string;
      status: string;
      features?: Record<string, boolean>;
    }>("/admin/v1/billing/dev-activate", {
      method: "POST",
      body,
    }),
  confirmCheckout: (body: { session_id: string }) =>
    request<{
      console_access: boolean;
      plan: string;
      status: string;
      message?: string;
    }>("/admin/v1/billing/confirm-checkout", {
      method: "POST",
      body,
    }),
  billingPortal: (body?: { return_url?: string }) =>
    request<{ mode: string; portal_url?: string; message?: string }>(
      "/admin/v1/billing/portal",
      { method: "POST", body: body ?? {} },
    ),
};

// --- Public (unauthenticated) API ----------------------------------------
export const publicApi = {
  signup: (body: {
    org_name: string;
    admin_email: string;
    password: string;
    full_name: string;
  }) =>
    request<{
      verification_token?: string;
      org_id?: string;
      slug?: string;
      message?: string;
    }>("/public/v1/signup", {
      method: "POST",
      body: {
        company_name: body.org_name,
        admin_email: body.admin_email,
        admin_password: body.password,
        admin_full_name: body.full_name,
      },
      auth: false,
    }),
  verifyEmail: (token: string) =>
    request<{
      org_id: string;
      slug: string;
      status: string;
      org_token: string;
      message: string;
    }>("/public/v1/verify-email", {
      auth: false,
      query: { token },
    }),
  contactSales: (body: {
    company: string;
    contact_name: string;
    email: string;
    phone: string;
    estimated_agents: number;
    message: string;
  }) =>
    request<{ id: string; message: string }>("/public/v1/contact-sales", {
      method: "POST",
      body: {
        // Live API (Docker) expects contact_email / estimated_seats.
        // Host commercial schema also accepts email / estimated_agents via aliases once rebuilt.
        company_name: body.company,
        contact_name: body.contact_name || null,
        contact_email: body.email,
        email: body.email,
        phone: body.phone || null,
        estimated_seats: body.estimated_agents || null,
        estimated_agents: body.estimated_agents || null,
        message: body.message || null,
      },
      auth: false,
    }),
  plans: (signal?: AbortSignal) =>
    request<{ plans: Record<string, unknown>[] }>("/public/v1/plans", {
      auth: false,
      signal,
    }),
};

/** WebSocket URL for live dashboard updates (admin scope). */
export function dashboardWebSocketUrl(token: string): string {
  // Prefer Kong directly for WS — Vite's HTTP proxy does not upgrade sockets reliably.
  const httpBase = API_URL || "http://localhost:8090";
  const wsBase = httpBase.replace(/^http/, "ws");
  const url = new URL("/admin/v1/ws/dashboard", wsBase.endsWith("/") ? wsBase : `${wsBase}/`);
  url.searchParams.set("token", token);
  return url.toString();
}

// --- Platform (vendor ops) API ------------------------------------------
export const platformApi = {
  login: (body: LoginRequest) =>
    request<TokenResponse>("/platform/v1/auth/login", {
      method: "POST",
      body,
      auth: false,
    }),
  me: (signal?: AbortSignal) =>
    request<PlatformUserResponse>("/platform/v1/auth/me", { signal }),
  updateProfile: (body: { full_name: string; email?: string }) =>
    request<PlatformUserResponse>("/platform/v1/auth/me", {
      method: "PATCH",
      body,
    }),
  changePassword: (body: {
    current_password: string;
    new_password: string;
  }) =>
    request<{ status: string; message: string }>(
      "/platform/v1/auth/change-password",
      { method: "POST", body },
    ),
  tenants: (signal?: AbortSignal) =>
    request<TenantListItem[]>("/platform/v1/tenants", { signal }),
  tenant: (orgId: string, signal?: AbortSignal) =>
    request<TenantDetailResponse>(`/platform/v1/tenants/${orgId}`, { signal }),
  usage: (orgId: string, signal?: AbortSignal) =>
    request<UsageResponse>(`/platform/v1/tenants/${orgId}/usage`, { signal }),
  suspend: (orgId: string, reason: string) =>
    request<{ status: string; org_id: string }>(
      `/platform/v1/tenants/${orgId}/suspend`,
      { method: "POST", body: { reason } },
    ),
  activate: (orgId: string) =>
    request<{ status: string; org_id: string }>(
      `/platform/v1/tenants/${orgId}/activate`,
      { method: "POST" },
    ),
  assignPlan: async (
    orgId: string,
    body: {
      plan: string;
      status?: string;
      max_agents?: number;
      max_users?: number;
      max_prompts_per_day?: number;
      max_prompts_per_month?: number;
      audit_retention_days?: number;
      activate?: boolean;
    },
  ) => {
    try {
      return await request<Record<string, unknown>>(
        `/platform/v1/tenants/${orgId}/assign-plan`,
        { method: "POST", body },
      );
    } catch (err) {
      // Docker SaaS image uses PATCH /subscription instead of assign-plan.
      if (!(err instanceof ApiError) || err.status !== 404) throw err;
      return request<Record<string, unknown>>(
        `/platform/v1/tenants/${orgId}/subscription`,
        {
          method: "PATCH",
          body: {
            plan: body.plan,
            status: body.status ?? (body.activate === false ? undefined : "active"),
            max_agents: body.max_agents,
            max_users: body.max_users,
            max_prompts_per_day: body.max_prompts_per_day,
            audit_retention_days: body.audit_retention_days,
          },
        },
      );
    }
  },
  leads: (signal?: AbortSignal) =>
    request<
      {
        id: string;
        company_name: string;
        contact_name: string | null;
        email?: string;
        contact_email?: string;
        phone?: string | null;
        estimated_agents?: number | null;
        estimated_seats?: number | null;
        message: string | null;
        status: string;
        org_id: string | null;
        notes: string | null;
        created_at: string;
      }[]
    >("/platform/v1/leads", { signal }),
  updateLead: (leadId: string, body: { status: string; notes?: string }) =>
    request<Record<string, unknown>>(`/platform/v1/leads/${leadId}`, {
      method: "PATCH",
      body,
    }),
  billingEvents: (signal?: AbortSignal) =>
    request<
      {
        id: string;
        org_id: string | null;
        stripe_event_id: string;
        event_type: string;
        processed_at: string;
      }[]
    >("/platform/v1/billing/events", { signal }),
  billingOverview: (signal?: AbortSignal) =>
    request<{
      total_tenants?: number;
      by_status?: Record<string, number>;
      by_plan?: Record<string, number>;
      mrr_cents?: number;
      [key: string]: unknown;
    }>("/platform/v1/billing/overview", { signal }),
};
