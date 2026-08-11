import type { LucideIcon } from "lucide-react";
import {
  BarChart3,
  Building2,
  CreditCard,
  Download,
  FileClock,
  Inbox,
  LayoutDashboard,
  ScrollText,
  Server,
  Settings,
  ShieldAlert,
  UserRound,
} from "lucide-react";

export interface NavItem {
  label: string;
  to: string;
  icon: LucideIcon;
  /** Required permission (backend semantics: `resource:*` grants any action). */
  permission?: string;
}

export interface NavSection {
  title: string;
  items: NavItem[];
}

export const adminNav: NavSection[] = [
  {
    title: "Overview",
    items: [
      { label: "Dashboard", to: "/dashboard", icon: LayoutDashboard },
      {
        label: "Threat Feed",
        to: "/threats",
        icon: ShieldAlert,
        permission: "threats:read",
      },
      {
        label: "Reports",
        to: "/reports",
        icon: BarChart3,
        permission: "dashboard:read",
      },
    ],
  },
  {
    title: "Security Operations",
    items: [
      {
        label: "Agent Fleet",
        to: "/agents",
        icon: Server,
        permission: "agents:read",
      },
      {
        label: "Download Agent",
        to: "/agents/download",
        icon: Download,
        permission: "agents:read",
      },
      {
        label: "Policies",
        to: "/policies",
        icon: ScrollText,
        permission: "policies:read",
      },
      {
        label: "Audit Log",
        to: "/audit",
        icon: FileClock,
        permission: "audit:read",
      },
    ],
  },
  {
    title: "Administration",
    items: [
      {
        label: "Billing",
        to: "/billing",
        icon: CreditCard,
      },
      {
        label: "Settings",
        to: "/settings",
        icon: Settings,
        permission: "users:read",
      },
      {
        label: "Account",
        to: "/account",
        icon: UserRound,
      },
    ],
  },
];

export const platformNav: NavSection[] = [
  {
    title: "Platform Operations",
    items: [
      {
        label: "Tenants",
        to: "/platform/tenants",
        icon: Building2,
        permission: "tenants:read",
      },
      {
        label: "Sales leads",
        to: "/platform/leads",
        icon: Inbox,
        permission: "tenants:read",
      },
      {
        label: "Account",
        to: "/platform/account",
        icon: UserRound,
      },
    ],
  },
];
