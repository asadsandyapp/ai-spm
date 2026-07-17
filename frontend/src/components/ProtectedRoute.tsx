import { Navigate, useLocation } from "react-router-dom";
import { useAuthStore, type AuthScope } from "@/stores/auth";

interface ProtectedRouteProps {
  scope: AuthScope;
  children: React.ReactNode;
}

export function ProtectedRoute({ scope, children }: ProtectedRouteProps) {
  const location = useLocation();
  const authed = useAuthStore((s) => s.isAuthenticated(scope));

  if (!authed) {
    const loginPath = scope === "admin" ? "/login" : "/platform/login";
    return <Navigate to={loginPath} state={{ from: location }} replace />;
  }

  return <>{children}</>;
}
