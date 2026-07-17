import { ShieldCheck } from "lucide-react";
import { cn } from "@/lib/utils";

interface LogoProps {
  variant?: "light" | "dark";
  showWordmark?: boolean;
  className?: string;
}

export function Logo({
  variant = "dark",
  showWordmark = true,
  className,
}: LogoProps) {
  const wordmarkColor = variant === "light" ? "text-white" : "text-ink-900";
  const subColor = variant === "light" ? "text-ink-300" : "text-ink-500";
  return (
    <div className={cn("flex items-center gap-2.5", className)}>
      <div className="grid h-9 w-9 place-items-center rounded-lg bg-gradient-to-br from-brand-400 to-brand-700 shadow-elevated">
        <ShieldCheck className="h-5 w-5 text-white" strokeWidth={2.2} />
      </div>
      {showWordmark && (
        <div className="leading-tight">
          <div className={cn("text-sm font-bold tracking-tight", wordmarkColor)}>
            AI-SPM
          </div>
          <div className={cn("text-[10px] font-medium uppercase tracking-wider", subColor)}>
            Security Posture
          </div>
        </div>
      )}
    </div>
  );
}
