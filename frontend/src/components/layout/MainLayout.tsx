import { Outlet, useNavigate } from "react-router-dom";
import { Sidebar } from "@/components/layout/Sidebar";
import { adminNav, platformNav } from "@/components/layout/nav";
import { useAuthStore, type AuthScope } from "@/stores/auth";
import { useMe } from "@/hooks/queries";

interface MainLayoutProps {
  scope: AuthScope;
}

export function MainLayout({ scope }: MainLayoutProps) {
  const navigate = useNavigate();
  const logout = useAuthStore((s) => s.logout);
  const claims = useAuthStore((s) => s.claims);

  // Only the tenant admin exposes a /me endpoint.
  const { data: me } = useMe(scope === "admin");

  const sections = scope === "admin" ? adminNav : platformNav;
  const loginPath = scope === "admin" ? "/login" : "/platform/login";

  const accountName =
    scope === "admin"
      ? (me?.full_name ?? me?.email ?? "Tenant Admin")
      : "Platform Operations";
  const accountSub = claims?.role ?? scope;

  const handleLogout = () => {
    logout();
    navigate(loginPath, { replace: true });
  };

  return (
    <div className="flex h-full overflow-hidden bg-ink-50">
      <Sidebar
        sections={sections}
        onLogout={handleLogout}
        accountName={accountName}
        accountSub={accountSub}
      />
      <main className="scroll-thin flex-1 overflow-y-auto">
        <div className="mx-auto max-w-[90rem] px-6 py-8 lg:px-8">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
