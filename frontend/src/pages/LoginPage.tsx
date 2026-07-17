import { useMutation } from "@tanstack/react-query";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { adminApi, ApiError } from "@/lib/api";
import { useAuthStore } from "@/stores/auth";
import { AuthLayout } from "@/pages/AuthLayout";
import { CredentialsForm } from "@/pages/CredentialsForm";
import type { LoginRequest } from "@/types/api";

export function LoginPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const setSession = useAuthStore((s) => s.setSession);

  const from =
    (location.state as { from?: { pathname?: string } } | null)?.from
      ?.pathname ?? "/dashboard";

  const mutation = useMutation({
    mutationFn: (body: LoginRequest) => adminApi.login(body),
    onSuccess: (res) => {
      setSession(res.access_token, "admin");
      navigate(from, { replace: true });
    },
  });

  const errorMessage =
    mutation.error instanceof ApiError
      ? mutation.error.detail
      : mutation.error
        ? "Unable to sign in. Please try again."
        : null;

  return (
    <AuthLayout
      eyebrow="Tenant Console"
      title="Sign in to your workspace"
      subtitle="Access your organization's AI security posture dashboard."
    >
      <CredentialsForm
        onSubmit={(email, password) => mutation.mutate({ email, password })}
        pending={mutation.isPending}
        error={errorMessage}
      />

      <div className="mt-6 space-y-3 text-center text-sm text-ink-500">
        <p>
          Need a workspace?{" "}
          <span className="font-medium text-ink-700">
            Contact your administrator to get provisioned.
          </span>
        </p>
        <p className="border-t border-ink-200 pt-3">
          <Link
            to="/platform/login"
            className="font-medium text-brand-600 hover:text-brand-700"
          >
            Platform operator sign in →
          </Link>
        </p>
      </div>
    </AuthLayout>
  );
}
