import { Link } from "react-router-dom";
import { Compass } from "lucide-react";
import { Logo } from "@/components/ui/Logo";

export function NotFoundPage() {
  return (
    <div className="flex min-h-full flex-col items-center justify-center gap-6 bg-ink-50 px-6 text-center">
      <Logo />
      <div className="grid h-14 w-14 place-items-center rounded-full bg-white shadow-card">
        <Compass className="h-6 w-6 text-brand-600" />
      </div>
      <div>
        <p className="text-5xl font-bold tracking-tight text-ink-900">404</p>
        <p className="mt-2 text-ink-500">
          The page you're looking for doesn't exist or has moved.
        </p>
      </div>
      <Link to="/dashboard" className="btn-primary">
        Back to dashboard
      </Link>
    </div>
  );
}
