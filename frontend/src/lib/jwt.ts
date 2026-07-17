import type { TokenClaims } from "@/types/api";

/**
 * Decode a JWT payload without verifying the signature. Verification is the
 * server's responsibility; the client only reads claims to gate UI/nav.
 */
export function decodeToken(token: string): TokenClaims | null {
  try {
    const payload = token.split(".")[1];
    if (!payload) return null;
    const normalized = payload.replace(/-/g, "+").replace(/_/g, "/");
    const padded = normalized.padEnd(
      normalized.length + ((4 - (normalized.length % 4)) % 4),
      "=",
    );
    const json = decodeURIComponent(
      atob(padded)
        .split("")
        .map((c) => "%" + c.charCodeAt(0).toString(16).padStart(2, "0"))
        .join(""),
    );
    return JSON.parse(json) as TokenClaims;
  } catch {
    return null;
  }
}

export function isTokenExpired(claims: TokenClaims | null): boolean {
  if (!claims?.exp) return true;
  // exp is seconds since epoch; add a small skew buffer.
  return Date.now() >= claims.exp * 1000 - 5_000;
}

/**
 * Permission check mirroring the backend's `require_permission` semantics:
 * a wildcard `resource:*` grants any action on that resource.
 */
export function hasPermission(
  permissions: string[] | undefined,
  required: string,
): boolean {
  if (!permissions?.length) return false;
  const [resource] = required.split(":");
  return permissions.includes(`${resource}:*`) || permissions.includes(required);
}
