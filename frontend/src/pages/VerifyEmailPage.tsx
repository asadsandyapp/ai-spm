import { useEffect, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { AlertCircle, CheckCircle2, Loader2 } from "lucide-react";
import { MarketingLayout } from "@/components/marketing/MarketingLayout";
import { ApiError, publicApi } from "@/lib/api";

export function VerifyEmailPage() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const token = searchParams.get("token") ?? "";
  const [manualToken, setManualToken] = useState(token);

  const mutation = useMutation({
    mutationFn: (verifyToken: string) => publicApi.verifyEmail(verifyToken),
    onSuccess: () => {
      navigate("/login", {
        replace: true,
        state: {
          message:
            "Email verified. Sign in to choose your plan and start protecting AI traffic.",
        },
      });
    },
  });

  useEffect(() => {
    if (token) {
      mutation.mutate(token);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  const errorMessage =
    mutation.error instanceof ApiError
      ? mutation.error.detail
      : mutation.error
        ? "Verification failed. Please try again or request a new link."
        : null;

  function handleManualSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (manualToken.trim()) {
      mutation.mutate(manualToken.trim());
    }
  }

  return (
    <MarketingLayout>
      <section className="mkt-page-hero border-b-0">
        <div className="mkt-shell flex min-h-[calc(100vh-5rem)] items-center py-16">
          <div className="mx-auto w-full max-w-lg text-center">
            {token && mutation.isPending ? (
              <>
                <Loader2 className="mx-auto h-12 w-12 animate-spin text-teal-400" />
                <h1 className="mt-7 font-display text-3xl font-bold text-white sm:text-4xl">
                  Verifying your email…
                </h1>
                <p className="mt-3 text-lg text-slate-400">
                  Please wait while we confirm your account.
                </p>
              </>
            ) : mutation.isSuccess ? (
              <>
                <CheckCircle2 className="mx-auto h-12 w-12 text-teal-400" />
                <h1 className="mt-7 font-display text-3xl font-bold text-white sm:text-4xl">
                  Email verified
                </h1>
                <p className="mt-3 text-lg text-slate-400">Redirecting to sign in…</p>
              </>
            ) : (
              <div className="mkt-panel p-8 text-left sm:p-10">
                <h1 className="text-center font-display text-3xl font-bold text-white sm:text-4xl">
                  Verify your email
                </h1>
                <p className="mt-3 text-center text-lg text-slate-400">
                  Check your inbox for a verification link, or paste your token below.
                </p>

                {errorMessage && (
                  <div className="mt-7 flex items-start gap-2.5 rounded-xl border border-rose-500/30 bg-rose-500/10 px-4 py-3.5 text-[17px] text-rose-200">
                    <AlertCircle className="mt-0.5 h-5 w-5 shrink-0" />
                    <span>{errorMessage}</span>
                  </div>
                )}

                <form onSubmit={handleManualSubmit} className="mt-7 space-y-5">
                  <div>
                    <label htmlFor="token" className="mkt-label">
                      Verification token
                    </label>
                    <input
                      id="token"
                      className="mkt-input font-mono text-sm"
                      value={manualToken}
                      onChange={(e) => setManualToken(e.target.value)}
                      placeholder="Paste token from email"
                    />
                  </div>
                  <button
                    type="submit"
                    className="mkt-btn-primary w-full"
                    disabled={mutation.isPending || !manualToken.trim()}
                  >
                    {mutation.isPending ? (
                      <>
                        <Loader2 className="h-5 w-5 animate-spin" />
                        Verifying…
                      </>
                    ) : (
                      "Verify email"
                    )}
                  </button>
                </form>

                <p className="mt-7 text-center text-base text-slate-500">
                  Already verified?{" "}
                  <Link to="/login" className="font-semibold text-teal-400 hover:text-teal-300">
                    Sign in
                  </Link>
                </p>
              </div>
            )}
          </div>
        </div>
      </section>
    </MarketingLayout>
  );
}
