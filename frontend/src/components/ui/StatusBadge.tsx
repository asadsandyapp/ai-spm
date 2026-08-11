import { cn, titleCase } from "@/lib/utils";

type Tone = "success" | "danger" | "warning" | "neutral" | "info";

const TONE_STYLES: Record<Tone, string> = {
  success: "bg-emerald-50 text-emerald-700 ring-1 ring-emerald-600/20",
  danger: "bg-rose-50 text-rose-700 ring-1 ring-rose-600/20",
  warning: "bg-amber-50 text-amber-700 ring-1 ring-amber-600/20",
  info: "bg-brand-50 text-brand-700 ring-1 ring-brand-600/20",
  neutral: "bg-ink-100 text-ink-600 ring-1 ring-ink-300",
};

const DOT_STYLES: Record<Tone, string> = {
  success: "bg-emerald-500",
  danger: "bg-rose-500",
  warning: "bg-amber-500",
  info: "bg-brand-500",
  neutral: "bg-ink-400",
};

function toneFor(status: string): Tone {
  switch ((status || "").toLowerCase()) {
    case "pending":
    case "incomplete":
    case "trialing":
    case "past_due":
    case "new":
    case "masked":
    case "pii_detected":
    case "policy_violation":
    case "medium":
      return "warning";
    case "contacted":
    case "prompt_submitted":
    case "low":
      return "info";
    case "won":
    case "online":
    case "active":
    case "allowed":
      return "success";
    case "lost":
    case "offline":
    case "inactive":
    case "suspended":
    case "revoked":
    case "blocked":
    case "deleted":
    case "threat_detected":
    case "prompt_blocked":
    case "high":
    case "canceled":
    case "expired":
      return "danger";
    default:
      return "neutral";
  }
}

interface StatusBadgeProps {
  status: string;
  pulse?: boolean;
  className?: string;
}

export function StatusBadge({ status, pulse, className }: StatusBadgeProps) {
  const safe = status || "unknown";
  const tone = toneFor(safe);
  const isLive = safe.toLowerCase() === "online";
  return (
    <span className={cn("badge", TONE_STYLES[tone], className)}>
      <span
        className={cn(
          "h-1.5 w-1.5 rounded-full",
          DOT_STYLES[tone],
          (pulse ?? isLive) && "animate-pulse-dot",
        )}
      />
      {titleCase(safe)}
    </span>
  );
}
