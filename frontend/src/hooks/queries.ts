import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { adminApi, platformApi } from "@/lib/api";
import type {
  CreatePolicyRequest,
  CreateUserRequest,
  LLMConfigRequest,
  ReportQuery,
  UpdatePiiDetectionRequest,
  UpdatePolicyRequest,
} from "@/types/api";

export const queryKeys = {
  me: ["admin", "me"] as const,
  platformMe: ["platform", "me"] as const,
  agents: ["admin", "agents"] as const,
  enrollment: ["admin", "agents", "enrollment"] as const,
  audit: (limit: number) => ["admin", "audit", limit] as const,
  policies: ["admin", "policies"] as const,
  piiDetections: ["admin", "pii-detections"] as const,
  dashboardMetrics: ["admin", "dashboard", "metrics"] as const,
  reportSummary: (params: ReportQuery) =>
    ["admin", "reports", "summary", params] as const,
  threats: (limit: number) => ["admin", "dashboard", "threats", limit] as const,
  users: ["admin", "users"] as const,
  llmConfigs: ["admin", "llm-configs"] as const,
  tenants: ["platform", "tenants"] as const,
  tenant: (orgId: string) => ["platform", "tenants", orgId] as const,
  billingOverview: ["platform", "billing", "overview"] as const,
};

export function useMe(enabled = true) {
  return useQuery({
    queryKey: queryKeys.me,
    queryFn: ({ signal }) => adminApi.me(signal),
    enabled,
    staleTime: 5 * 60 * 1000,
  });
}

export function useAgents() {
  return useQuery({
    queryKey: queryKeys.agents,
    queryFn: ({ signal }) => adminApi.agents(signal),
    refetchInterval: 30_000,
  });
}

export function useEnrollment() {
  return useQuery({
    queryKey: queryKeys.enrollment,
    queryFn: ({ signal }) => adminApi.enrollment(signal),
  });
}

export function useRotateOrgToken() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => adminApi.rotateOrgToken(),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.enrollment }),
  });
}

export function useDownloadLinuxInstaller() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => adminApi.downloadLinuxInstaller(),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.enrollment }),
  });
}

export function useAudit(limit = 50) {
  return useQuery({
    queryKey: queryKeys.audit(limit),
    queryFn: ({ signal }) => adminApi.audit({ limit }, signal),
    refetchInterval: 30_000,
  });
}

export function usePolicies() {
  return useQuery({
    queryKey: queryKeys.policies,
    queryFn: ({ signal }) => adminApi.policies(signal),
  });
}

export function usePiiDetections() {
  return useQuery({
    queryKey: queryKeys.piiDetections,
    queryFn: ({ signal }) => adminApi.piiDetections(signal),
  });
}

export function useUpdatePiiDetection() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      id,
      body,
    }: {
      id: string;
      body: UpdatePiiDetectionRequest;
    }) => adminApi.updatePiiDetection(id, body),
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: queryKeys.piiDetections }),
  });
}

export function useDashboardMetrics() {
  return useQuery({
    queryKey: queryKeys.dashboardMetrics,
    queryFn: ({ signal }) => adminApi.dashboardMetrics(signal),
    refetchInterval: 30_000,
  });
}

export function useReportSummary(params: ReportQuery) {
  return useQuery({
    queryKey: queryKeys.reportSummary(params),
    queryFn: ({ signal }) => adminApi.reportSummary(params, signal),
    staleTime: 30_000,
    placeholderData: (prev) => prev,
  });
}

export function useThreats(limit = 50, opts?: { enabled?: boolean }) {
  return useQuery({
    queryKey: queryKeys.threats(limit),
    queryFn: ({ signal }) => adminApi.dashboardThreats(limit, signal),
    refetchInterval: 30_000,
    enabled: opts?.enabled ?? true,
  });
}

export function useCreatePolicy() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: CreatePolicyRequest) => adminApi.createPolicy(body),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.policies }),
  });
}

export function useUpdatePolicy() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: UpdatePolicyRequest }) =>
      adminApi.updatePolicy(id, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.policies }),
  });
}

export function useDeletePolicy() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => adminApi.deletePolicy(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.policies }),
  });
}

export function useRevokeAgent() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => adminApi.revokeAgent(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.agents }),
  });
}

export function useDeleteAgent() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      id,
      purge_data,
    }: {
      id: string;
      purge_data?: boolean;
    }) => adminApi.deleteAgent(id, { purge_data }),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.agents }),
  });
}

export function useExportAudit() {
  return useMutation({
    mutationFn: (days: number) => adminApi.downloadAuditExport(days),
  });
}

export function useUsers() {
  return useQuery({
    queryKey: queryKeys.users,
    queryFn: ({ signal }) => adminApi.users(signal),
  });
}

export function useCreateUser() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: CreateUserRequest) => adminApi.createUser(body),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.users }),
  });
}

export function useLlmConfigs() {
  return useQuery({
    queryKey: queryKeys.llmConfigs,
    queryFn: ({ signal }) => adminApi.llmConfigs(signal),
  });
}

export function useUpsertLlmConfig() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: LLMConfigRequest) => adminApi.upsertLlmConfig(body),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.llmConfigs }),
  });
}

export function useTenants() {
  return useQuery({
    queryKey: queryKeys.tenants,
    queryFn: ({ signal }) => platformApi.tenants(signal),
    refetchInterval: 60_000,
  });
}

export function useTenant(orgId: string | undefined) {
  return useQuery({
    queryKey: queryKeys.tenant(orgId ?? ""),
    queryFn: ({ signal }) => platformApi.tenant(orgId!, signal),
    enabled: Boolean(orgId),
  });
}

export function usePlatformMe(enabled = true) {
  return useQuery({
    queryKey: queryKeys.platformMe,
    queryFn: ({ signal }) => platformApi.me(signal),
    enabled,
    staleTime: 5 * 60 * 1000,
    retry: false,
  });
}

export function useBillingOverview(enabled = true) {
  return useQuery({
    queryKey: queryKeys.billingOverview,
    queryFn: ({ signal }) => platformApi.billingOverview(signal),
    enabled,
    retry: false,
  });
}
