import { useMutation } from "@tanstack/react-query";
import { Link, useLocation, useNavigate, useSearchParams } from "react-router-dom";
import { adminApi, platformApi, ApiError } from "@/lib/api";
import { useAuthStore } from "@/stores/auth";
import { AuthLayout } from "@/pages/AuthLayout";
import { CredentialsForm } from "@/pages/CredentialsForm";

export function LoginPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const [searchParams] = useSearchParams();
  const setSession = useAuthStore((s) => s.setSession);

  const banner =
    (location.state as { message?: string } | null)?.message ?? null;

  const fromPath =
    (location.state as { from?: { pathname?: string } } | null)?.from
      ?.pathname ?? null;

  const nextPath = searchParams.get("next");
  const returnTo =
    nextPath && nextPath.startsWith("/") && !nextPath.startsWith("//")
      ? nextPath
      : fromPath;

  const mutation = useMutation({
    mutationFn: async (body: { email: string; password: string }) => {
      // Resolve portal from credentials: company admin first, then platform.
      try {
        const res = await adminApi.login(body);
        setSession(res.access_token, "admin");
        const me = await adminApi.me();
        return { scope: "admin" as const, me };
      } catch (adminErr) {
        if (!(adminErr instanceof ApiError) || adminErr.status !== 401) {
          throw adminErr;
        }
      }

      try {
        const res = await platformApi.login(body);
        setSession(res.access_token, "platform");
        return { scope: "platform" as const, me: null };
      } catch (platformErr) {
        if (platformErr instanceof ApiError && platformErr.status === 401) {
          throw new ApiError(401, "Invalid email or password.");
        }
        throw platformErr;
      }
    },
    onSuccess: ({ scope, me }) => {
      if (scope === "platform") {
        const dest =
          returnTo && returnTo.startsWith("/platform")
            ? returnTo
            : "/platform/tenants";
        navigate(dest, { replace: true });
        return;
      }
      if (me && !me.console_access) {
        if (returnTo?.startsWith("/billing/success")) {
          navigate(returnTo, { replace: true });
          return;
        }
        navigate("/onboarding/plans", { replace: true });
        return;
      }
      const dest =
        !returnTo ||
        returnTo.startsWith("/onboarding") ||
        returnTo === "/login" ||
        returnTo.startsWith("/platform")
          ? "/dashboard"
          : returnTo;
      navigate(dest, { replace: true });
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
      eyebrow="Secure access"
      title="Welcome back"
      subtitle="Sign in with your work email to continue to your organization’s AI security workspace."
    >
      {banner && (
        <div className="mb-5 rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm leading-relaxed text-emerald-800">
          {banner}
        </div>
      )}

      <CredentialsForm
        onSubmit={(email, password) => mutation.mutate({ email, password })}
        pending={mutation.isPending}
        error={errorMessage}
        emailLabel="Work email"
        submitLabel="Continue"
      />

      <div className="mt-7 border-t border-ink-100 pt-6 text-center text-sm text-ink-500">
        <p>
          New to AI-SPM?{" "}
          <Link
            to="/signup"
            className="font-semibold text-brand-600 transition-colors hover:text-brand-700"
          >
            Create your workspace
          </Link>
        </p>
      </div>
    </AuthLayout>
  );
}
