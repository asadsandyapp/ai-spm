import { useMutation } from "@tanstack/react-query";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { platformApi, ApiError } from "@/lib/api";
import { useAuthStore } from "@/stores/auth";
import { AuthLayout } from "@/pages/AuthLayout";
import { CredentialsForm } from "@/pages/CredentialsForm";
import type { LoginRequest } from "@/types/api";

export function PlatformLoginPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const setSession = useAuthStore((s) => s.setSession);

  const from =
    (location.state as { from?: { pathname?: string } } | null)?.from
      ?.pathname ?? "/platform/tenants";

  const mutation = useMutation({
    mutationFn: (body: LoginRequest) => platformApi.login(body),
    onSuccess: (res) => {
      setSession(res.access_token, "platform");
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
      eyebrow="Platform Operations"
      title="Operator sign in"
      subtitle="Restricted access for AI-SPM platform administrators."
    >
      <CredentialsForm
        onSubmit={(email, password) => mutation.mutate({ email, password })}
        pending={mutation.isPending}
        error={errorMessage}
        emailLabel="Operator email"
        submitLabel="Access platform console"
      />

      <div className="mt-6 text-center text-sm text-ink-500">
        <p className="border-t border-ink-200 pt-3">
          <Link
            to="/login"
            className="font-medium text-brand-600 hover:text-brand-700"
          >
            ← Back to tenant sign in
          </Link>
        </p>
      </div>
    </AuthLayout>
  );
}
