import { Link, NavLink } from "react-router-dom";
import { LogOut } from "lucide-react";
import { Logo } from "@/components/ui/Logo";
import { useAuthStore } from "@/stores/auth";
import { hasPermission } from "@/lib/jwt";
import { cn, initials, titleCase } from "@/lib/utils";
import type { NavSection } from "@/components/layout/nav";

interface SidebarProps {
  sections: NavSection[];
  onLogout: () => void;
  /** Display name for the account footer (e.g. user email or "Platform Ops"). */
  accountName: string;
  accountSub: string;
  /** Route for profile / account settings. */
  accountTo?: string;
}

export function Sidebar({
  sections,
  onLogout,
  accountName,
  accountSub,
  accountTo,
}: SidebarProps) {
  const permissions = useAuthStore((s) => s.permissions());

  return (
    <aside className="flex h-full w-64 shrink-0 flex-col border-r border-ink-800 bg-ink-900">
      <div className="flex h-16 items-center border-b border-ink-800 px-5">
        <Logo variant="light" />
      </div>

      <nav className="scroll-thin flex-1 space-y-6 overflow-y-auto px-3 py-5">
        {sections.map((section) => {
          const visible = section.items.filter(
            (item) =>
              !item.permission || hasPermission(permissions, item.permission),
          );
          if (visible.length === 0) return null;
          return (
            <div key={section.title}>
              <p className="px-3 pb-2 text-[10px] font-semibold uppercase tracking-wider text-ink-500">
                {section.title}
              </p>
              <ul className="space-y-1">
                {visible.map((item) => (
                  <li key={item.to}>
                    <NavLink
                      to={item.to}
                      end={item.to === "/platform/tenants"}
                      className={({ isActive }) =>
                        cn(
                          "group flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors",
                          isActive
                            ? "bg-brand-600/15 text-white ring-1 ring-inset ring-brand-500/30"
                            : "text-ink-300 hover:bg-ink-800 hover:text-white",
                        )
                      }
                    >
                      <item.icon
                        className="h-[18px] w-[18px] shrink-0"
                        strokeWidth={2}
                      />
                      {item.label}
                    </NavLink>
                  </li>
                ))}
              </ul>
            </div>
          );
        })}
      </nav>

      <div className="border-t border-ink-800 p-3">
        <div className="flex items-center gap-3 rounded-lg px-2 py-2">
          {accountTo ? (
            <Link
              to={accountTo}
              className="flex min-w-0 flex-1 items-center gap-3 rounded-md hover:opacity-90"
              title="Account settings"
            >
              <div className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-brand-600 text-xs font-semibold text-white">
                {initials(accountName) || "AI"}
              </div>
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium text-white">
                  {accountName}
                </p>
                <p className="truncate text-xs text-ink-400">
                  {titleCase(accountSub)}
                </p>
              </div>
            </Link>
          ) : (
            <>
              <div className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-brand-600 text-xs font-semibold text-white">
                {initials(accountName) || "AI"}
              </div>
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium text-white">
                  {accountName}
                </p>
                <p className="truncate text-xs text-ink-400">
                  {titleCase(accountSub)}
                </p>
              </div>
            </>
          )}
          <button
            onClick={onLogout}
            title="Sign out"
            className="rounded-md p-2 text-ink-400 transition-colors hover:bg-ink-800 hover:text-white"
          >
            <LogOut className="h-4 w-4" />
          </button>
        </div>
      </div>
    </aside>
  );
}
