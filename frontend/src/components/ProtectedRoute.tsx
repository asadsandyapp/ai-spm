import { useEffect, useState } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { useAuthStore, type AuthScope } from "@/stores/auth";
import { adminApi } from "@/lib/api";
import { Spinner } from "@/components/ui/States";

interface ProtectedRouteProps {
  scope: AuthScope;
  children: React.ReactNode;
  /** Skip subscription gate (onboarding / billing funnel). */
  allowUnpaid?: boolean;
}

const ONBOARDING_PREFIXES = [
  "/onboarding",
  "/billing/success",
  "/billing/cancel",
  "/checkout",
  "/account",
];

function isOnboardingPath(pathname: string): boolean {
  return ONBOARDING_PREFIXES.some(
    (p) => pathname === p || pathname.startsWith(`${p}/`),
  );
}

export function ProtectedRoute({
  scope,
  children,
  allowUnpaid = false,
}: ProtectedRouteProps) {
  const location = useLocation();
  const authed = useAuthStore((s) => s.isAuthenticated(scope));
  const [consoleAccess, setConsoleAccess] = useState<boolean | null>(
    scope === "platform" || allowUnpaid ? true : null,
  );

  useEffect(() => {
    if (scope !== "admin" || !authed || allowUnpaid) {
      setConsoleAccess(true);
      return;
    }
    if (isOnboardingPath(location.pathname)) {
      setConsoleAccess(true);
      return;
    }
    let cancelled = false;
    setConsoleAccess(null);
    adminApi
      .me()
      .then((me) => {
        if (!cancelled) setConsoleAccess(Boolean(me.console_access));
      })
      .catch(() => {
        if (!cancelled) setConsoleAccess(false);
      });
    return () => {
      cancelled = true;
    };
  }, [scope, authed, allowUnpaid, location.pathname]);

  if (!authed) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  if (scope === "admin" && !allowUnpaid && !isOnboardingPath(location.pathname)) {
    if (consoleAccess === null) {
      return (
        <div className="flex min-h-screen items-center justify-center bg-ink-50">
          <Spinner />
        </div>
      );
    }
    if (!consoleAccess) {
      return <Navigate to="/onboarding/plans" replace />;
    }
  }

  return <>{children}</>;
}
