import { create } from "zustand";
import { decodeToken, isTokenExpired } from "@/lib/jwt";
import type { TokenClaims } from "@/types/api";

export type AuthScope = "admin" | "platform";

interface AuthState {
  token: string | null;
  claims: TokenClaims | null;
  scope: AuthScope | null;
  setSession: (token: string, scope: AuthScope) => void;
  logout: () => void;
  isAuthenticated: (scope?: AuthScope) => boolean;
  permissions: () => string[];
}

/**
 * Session persistence: the JWT is written to sessionStorage so a page
 * refresh does not drop the session (and bounce the user to login).
 * sessionStorage (not localStorage) keeps the token scoped to the tab and
 * clears it when the browser/tab closes.
 */
const STORAGE_KEY = "ai-spm.session";

interface PersistedSession {
  token: string;
  scope: AuthScope;
}

function loadSession(): { token: string | null; claims: TokenClaims | null; scope: AuthScope | null } {
  const empty = { token: null, claims: null, scope: null };
  if (typeof window === "undefined") return empty;
  try {
    const raw = window.sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return empty;
    const parsed = JSON.parse(raw) as PersistedSession;
    const claims = decodeToken(parsed.token);
    if (!claims || isTokenExpired(claims)) {
      window.sessionStorage.removeItem(STORAGE_KEY);
      return empty;
    }
    return { token: parsed.token, claims, scope: parsed.scope };
  } catch {
    return empty;
  }
}

function persistSession(session: PersistedSession | null): void {
  if (typeof window === "undefined") return;
  try {
    if (session) {
      window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(session));
    } else {
      window.sessionStorage.removeItem(STORAGE_KEY);
    }
  } catch {
    /* storage unavailable (private mode / quota) — degrade to in-memory */
  }
}

export const useAuthStore = create<AuthState>((set, get) => ({
  ...loadSession(),

  setSession: (token, scope) => {
    const claims = decodeToken(token);
    persistSession({ token, scope });
    set({ token, claims, scope });
  },

  logout: () => {
    persistSession(null);
    set({ token: null, claims: null, scope: null });
  },

  isAuthenticated: (scope) => {
    const { token, claims, scope: current } = get();
    if (!token || isTokenExpired(claims)) return false;
    if (scope && current !== scope) return false;
    return true;
  },

  permissions: () => get().claims?.permissions ?? [],
}));

/** Non-hook accessor for use in the API client / interceptors. */
export function getAuthToken(): string | null {
  const { token, claims } = useAuthStore.getState();
  if (!token || isTokenExpired(claims)) return null;
  return token;
}
