import { useEffect, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { AlertCircle, CheckCircle2, Loader2 } from "lucide-react";
import { ApiError, adminApi } from "@/lib/api";
import { useAuthStore } from "@/stores/auth";

export function BillingSuccessPage() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated("admin"));
  const isDev = searchParams.get("dev") === "1";
  const sessionId = searchParams.get("session_id");
  const needsActivation = isDev || Boolean(sessionId);
  const [done, setDone] = useState(!needsActivation);
  const returnPath = `/billing/success?${searchParams.toString()}`;

  const mutation = useMutation({
    mutationFn: () => {
      if (sessionId) {
        return adminApi.confirmCheckout({ session_id: sessionId });
      }
      const plan = searchParams.get("plan") || "starter";
      return adminApi.devActivate({ plan });
    },
    onSuccess: (res) => {
      setDone(true);
      if (res.console_access) {
        setTimeout(() => navigate("/dashboard", { replace: true }), 1200);
      }
    },
  });

  useEffect(() => {
    if (needsActivation && isAuthenticated) {
      mutation.mutate();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [needsActivation, sessionId, isDev, isAuthenticated]);

  const errorMessage = (() => {
    if (!mutation.error) return null;
    if (mutation.error instanceof ApiError) {
      if (mutation.error.status === 0) {
        return (
          "Could not reach the API. If you use Vite dev (port 5173), restart it after pulling " +
          "latest changes so the /admin proxy is active."
        );
      }
      if (mutation.error.status === 401) {
        return "Your session expired. Log in with the same account you used for checkout, then return here.";
      }
      if (mutation.error.status === 403) {
        return "This checkout belongs to a different organization. Log in with the account that started checkout.";
      }
      return mutation.error.detail;
    }
    return "Activation failed. Please contact support.";
  })();

  return (
    <div className="flex min-h-full items-center justify-center bg-ink-50 px-6 py-12">
      <div className="w-full max-w-md animate-fade-in text-center">
        {needsActivation && mutation.isPending ? (
          <>
            <Loader2 className="mx-auto h-10 w-10 animate-spin text-brand-600" />
            <h1 className="mt-6 text-xl font-semibold text-ink-900">
              Activating your subscription…
            </h1>
            <p className="mt-2 text-sm text-ink-500">
              {sessionId
                ? "Confirming your Stripe payment with AI-SPM…"
                : "Dev mode — skipping Stripe webhook."}
            </p>
          </>
        ) : needsActivation && !isAuthenticated ? (
          <>
            <AlertCircle className="mx-auto h-10 w-10 text-amber-500" />
            <h1 className="mt-6 text-xl font-semibold text-ink-900">Log in to activate</h1>
            <p className="mt-2 text-sm text-ink-500">
              Payment succeeded in Stripe. Sign in with the same account you used for checkout to
              finish activation.
            </p>
            <Link
              to={`/login?next=${encodeURIComponent(returnPath)}`}
              className="btn-primary mt-6 inline-flex"
            >
              Log in
            </Link>
          </>
        ) : errorMessage ? (
          <>
            <AlertCircle className="mx-auto h-10 w-10 text-rose-500" />
            <h1 className="mt-6 text-xl font-semibold text-ink-900">Activation failed</h1>
            <p className="mt-2 text-sm text-rose-600">{errorMessage}</p>
            <Link to="/onboarding/plans" className="btn-primary mt-6 inline-flex">
              Back to plans
            </Link>
          </>
        ) : done ? (
          <>
            <CheckCircle2 className="mx-auto h-10 w-10 text-emerald-600" />
            <h1 className="mt-6 text-xl font-semibold text-ink-900">
              Subscription active
            </h1>
            <p className="mt-2 text-sm text-ink-500">
              {needsActivation
                ? "Payment confirmed. Redirecting to your console…"
                : "Your payment was successful. You can now deploy agents and configure policies."}
            </p>
            <Link to="/dashboard" className="btn-primary mt-6 inline-flex">
              Go to dashboard
            </Link>
          </>
        ) : (
          <>
            <Loader2 className="mx-auto h-10 w-10 animate-spin text-brand-600" />
            <h1 className="mt-6 text-xl font-semibold text-ink-900">Processing…</h1>
          </>
        )}
      </div>
    </div>
  );
}
