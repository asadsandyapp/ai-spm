// Type definitions mirroring the AI-SPM backend response models
// (see backend/src/ai_spm/core/schemas.py). Keep these in sync with the API.

export type UserRole =
  | "super_admin"
  | "security_admin"
  | "auditor"
  | "viewer";

export type PlatformRole =
  | "platform_super"
  | "platform_support"
  | "platform_billing";

export type AgentStatus = "pending" | "online" | "offline" | "revoked";

export type OrganizationStatus =
  | "pending"
  | "active"
  | "suspended"
  | "deleted";

export type SubscriptionPlan = "free" | "pro" | "enterprise";

export interface LoginRequest {
  email: string;
  password: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
}

export interface UserResponse {
  id: string;
  email: string;
  full_name: string;
  role: UserRole;
  org_id: string;
}

export interface AgentResponse {
  id: string;
  org_id: string;
  hostname: string;
  status: AgentStatus;
  os_version: string | null;
  agent_version: string | null;
  last_heartbeat_at: string | null;
}

export interface EnrollmentInfoResponse {
  org_id: string;
  org_name: string;
  org_slug: string;
  gateway_url: string;
  has_token: boolean;
  installer_linux_ready: boolean;
}

export interface OrgTokenRotateResponse {
  org_id: string;
  org_token: string;
  message: string;
}

export interface AuditEventResponse {
  id: string;
  event_type: string;
  agent_id: string | null;
  hostname: string | null;
  provider: string | null;
  masked_content: string | null;
  /** Unmasked user prompt (admin investigation; may contain PII). */
  original_content: string | null;
  /** Entity types found — never raw PII values. */
  pii_entities: string[];
  pii_hit_count: number;
  source: string | null;
  created_at: string;
}

export interface PolicyResponse {
  id: string;
  name: string;
  description: string | null;
  rules: Record<string, unknown>;
  is_default: boolean;
  is_active: boolean;
}

export interface PiiDetectionPolicy {
  id: string;
  name: string;
  category: string;
  description: string;
  mask: string;
  detectable: boolean;
  enabled: boolean;
  status: string;
}

export interface UpdatePiiDetectionRequest {
  enabled: boolean;
}

export interface TenantListItem {
  id: string;
  slug: string;
  name: string;
  status: OrganizationStatus;
  created_at: string;
  agent_count: number;
  plan: SubscriptionPlan | string;
}

export interface TenantDetailResponse extends TenantListItem {
  prompts_today: number;
  max_agents: number;
  max_prompts_per_day: number;
}

export interface UsageResponse {
  agent_count: number;
  prompts_today: number;
  max_agents: number;
  max_prompts_per_day: number;
  plan: SubscriptionPlan | string;
}

export interface DailyActivityPoint {
  date: string;
  count: number;
}

export interface DashboardMetricsResponse {
  prompts_24h: number;
  blocks_24h: number;
  pii_detections_24h: number;
  threats_24h: number;
  agents_total: number;
  agents_online: number;
  security_score: number;
  daily_activity: DailyActivityPoint[];
}

export interface ThreatEventResponse {
  id: string;
  event_type: string;
  severity: string;
  masked_content: string;
  original_content: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
  agent_id: string | null;
  hostname: string | null;
  provider: string | null;
}

export interface CreatePolicyRequest {
  name: string;
  description?: string | null;
  rules: Record<string, unknown>;
  is_default?: boolean;
}

export interface UpdatePolicyRequest {
  name?: string;
  description?: string | null;
  rules?: Record<string, unknown>;
  is_active?: boolean;
}

export interface CreateUserRequest {
  email: string;
  password: string;
  full_name: string;
  role?: UserRole;
}

export interface LLMConfigRequest {
  provider: string;
  api_key: string;
  is_active?: boolean;
}

export interface LLMConfigResponse {
  id: string;
  provider: string;
  is_active: boolean;
}

export interface AuditExportResponse {
  format: string;
  row_count: number;
  download_url: string;
}

export interface DashboardWebSocketUpdate {
  type: "dashboard_update";
  metrics: DashboardMetricsResponse;
  threats: ThreatEventResponse[];
}

export interface DashboardWebSocketEvent {
  type: "event";
  payload: Record<string, unknown>;
}

export type DashboardWebSocketMessage =
  | DashboardWebSocketUpdate
  | DashboardWebSocketEvent;

// Decoded JWT claims (admin + platform tokens share this shape).
export interface TokenClaims {
  sub: string;
  role: string;
  permissions: string[];
  exp: number;
  type: "admin" | "platform";
  org_id?: string;
}
