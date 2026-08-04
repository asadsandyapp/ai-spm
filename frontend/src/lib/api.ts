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
  (import.meta.env.VITE_API_URL as string | undefined)?.replace(/\/$/, "") ??
  "http://localhost:8080";

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

  const url = new URL(`${API_URL}${path}`);
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

  if (res.status === 401 && auth) {
    // Token rejected/expired — clear the in-memory session.
    useAuthStore.getState().logout();
  }

  if (!res.ok) {
    let detail = `Request failed with status ${res.status}`;
    try {
      const data = await res.json();
      if (typeof data?.detail === "string") detail = data.detail;
      else if (Array.isArray(data?.detail) && data.detail[0]?.msg)
        detail = data.detail[0].msg;
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
  deleteAgent: (id: string) =>
    request<void>(`/admin/v1/agents/${id}`, { method: "DELETE" }),
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
    const url = new URL(`${API_URL}/admin/v1/agents/installer/linux`);
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
    const url = new URL(`${API_URL}/admin/v1/audit/export/download`);
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
};

/** WebSocket URL for live dashboard updates (admin scope). */
export function dashboardWebSocketUrl(token: string): string {
  const base = API_URL.replace(/^http/, "ws");
  const url = new URL(`${base}/admin/v1/ws/dashboard`);
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
};
