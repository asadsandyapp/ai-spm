import type { LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";

interface MetricCardProps {
  label: string;
  value: string | number;
  icon: LucideIcon;
  hint?: string;
  trend?: { value: string; direction: "up" | "down" | "flat" };
  accent?: "brand" | "emerald" | "amber" | "rose" | "violet";
  loading?: boolean;
}

const ACCENTS: Record<NonNullable<MetricCardProps["accent"]>, string> = {
  brand: "bg-brand-50 text-brand-600",
  emerald: "bg-emerald-50 text-emerald-600",
  amber: "bg-amber-50 text-amber-600",
  rose: "bg-rose-50 text-rose-600",
  violet: "bg-violet-50 text-violet-600",
};

const TREND_STYLES = {
  up: "text-emerald-600",
  down: "text-rose-600",
  flat: "text-ink-500",
};

export function MetricCard({
  label,
  value,
  icon: Icon,
  hint,
  trend,
  accent = "brand",
  loading,
}: MetricCardProps) {
  return (
    <div className="card animate-fade-in p-5">
      <div className="flex items-start justify-between">
        <div className="min-w-0">
          <p className="text-sm font-medium text-ink-500">{label}</p>
          {loading ? (
            <div className="mt-2 h-8 w-20 animate-pulse rounded bg-ink-100" />
          ) : (
            <p className="mt-1.5 text-3xl font-semibold tracking-tight text-ink-900">
              {value}
            </p>
          )}
          {(hint || trend) && !loading && (
            <p className="mt-1.5 flex items-center gap-1.5 text-xs text-ink-500">
              {trend && (
                <span className={cn("font-semibold", TREND_STYLES[trend.direction])}>
                  {trend.value}
                </span>
              )}
              {hint}
            </p>
          )}
        </div>
        <div className={cn("rounded-lg p-2.5", ACCENTS[accent])}>
          <Icon className="h-5 w-5" strokeWidth={2} />
        </div>
      </div>
    </div>
  );
}
