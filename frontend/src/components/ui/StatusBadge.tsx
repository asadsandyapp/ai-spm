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
  switch (status.toLowerCase()) {
    case "online":
    case "active":
    case "allowed":
      return "success";
    case "offline":
    case "inactive":
    case "suspended":
    case "revoked":
    case "blocked":
    case "deleted":
      return "danger";
    case "pending":
    case "trialing":
    case "past_due":
    case "masked":
      return "warning";
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
  const tone = toneFor(status);
  const isLive = status.toLowerCase() === "online";
  return (
    <span className={cn("badge", TONE_STYLES[tone], className)}>
      <span
        className={cn(
          "h-1.5 w-1.5 rounded-full",
          DOT_STYLES[tone],
          (pulse ?? isLive) && "animate-pulse-dot",
        )}
      />
      {titleCase(status)}
    </span>
  );
}
