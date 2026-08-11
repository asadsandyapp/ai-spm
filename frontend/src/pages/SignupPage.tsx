import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";
import { AlertCircle, ArrowRight, Eye, EyeOff, Loader2 } from "lucide-react";
import { MarketingLayout } from "@/components/marketing/MarketingLayout";
import { ApiError, publicApi } from "@/lib/api";

interface SignupForm {
  org_name: string;
  admin_email: string;
  password: string;
  full_name: string;
}

export function SignupPage() {
  const navigate = useNavigate();
  const [form, setForm] = useState<SignupForm>({
    org_name: "",
    admin_email: "",
    password: "",
    full_name: "",
  });
  const [showPassword, setShowPassword] = useState(false);

  const mutation = useMutation({
    mutationFn: (body: SignupForm) => publicApi.signup(body),
    onSuccess: (res) => {
      const token = (res as { verification_token?: string }).verification_token;
      if (token) {
        navigate(`/verify?token=${encodeURIComponent(token)}`);
      } else {
        navigate("/verify");
      }
    },
  });

  const errorMessage =
    mutation.error instanceof ApiError
      ? mutation.error.detail
      : mutation.error
        ? "Unable to create your workspace. Please try again."
        : null;

  function handleChange(e: React.ChangeEvent<HTMLInputElement>) {
    setForm((prev) => ({ ...prev, [e.target.name]: e.target.value }));
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    mutation.mutate(form);
  }

  return (
    <MarketingLayout>
      <section className="mkt-page-hero">
        <div
          className="pointer-events-none absolute inset-0"
          style={{
            background:
              "radial-gradient(44rem 28rem at 55% 5%, rgba(45,212,191,0.13), transparent 55%)",
          }}
        />
        <div className="mkt-shell relative grid items-start gap-12 py-16 lg:grid-cols-[1fr_1.1fr] lg:gap-16 lg:py-20">
          <div className="lg:sticky lg:top-28">
            <p className="mkt-eyebrow">Get started</p>
            <h1 className="mkt-h1 mt-4">Create your workspace</h1>
            <p className="mkt-lead mt-6 text-slate-200">
              Set up your organization and verify your admin email to begin protecting AI traffic
              across every endpoint.
            </p>
            <ul className="mt-10 hidden space-y-4 text-lg text-slate-400 lg:block">
              {[
                "Guided agent installer for your organization",
                "Protect AI apps and ChatGPT / Claude / Gemini",
                "Console unlocks after active subscription",
              ].map((item) => (
                <li key={item} className="flex gap-3">
                  <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-teal-400" />
                  {item}
                </li>
              ))}
            </ul>
          </div>

          <div>
            <form onSubmit={handleSubmit} className="mkt-panel space-y-5 p-8 sm:p-10">
              {errorMessage && (
                <div className="flex items-start gap-2.5 rounded-xl border border-rose-500/30 bg-rose-500/10 px-4 py-3.5 text-base text-rose-200">
                  <AlertCircle className="mt-0.5 h-5 w-5 shrink-0" />
                  <span>{errorMessage}</span>
                </div>
              )}

              <div>
                <label htmlFor="org_name" className="mkt-label">
                  Organization name
                </label>
                <input
                  id="org_name"
                  name="org_name"
                  className="mkt-input"
                  placeholder="Acme Corp"
                  value={form.org_name}
                  onChange={handleChange}
                  required
                  autoFocus
                />
              </div>

              <div>
                <label htmlFor="full_name" className="mkt-label">
                  Your full name
                </label>
                <input
                  id="full_name"
                  name="full_name"
                  className="mkt-input"
                  placeholder="Jane Smith"
                  value={form.full_name}
                  onChange={handleChange}
                  required
                />
              </div>

              <div>
                <label htmlFor="admin_email" className="mkt-label">
                  Admin email
                </label>
                <input
                  id="admin_email"
                  name="admin_email"
                  type="email"
                  className="mkt-input"
                  placeholder="you@company.com"
                  value={form.admin_email}
                  onChange={handleChange}
                  required
                />
              </div>

              <div>
                <label htmlFor="password" className="mkt-label">
                  Password
                </label>
                <div className="relative">
                  <input
                    id="password"
                    name="password"
                    type={showPassword ? "text" : "password"}
                    className="mkt-input pr-12"
                    placeholder="Minimum 12 characters"
                    value={form.password}
                    onChange={handleChange}
                    minLength={12}
                    required
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword((s) => !s)}
                    className="absolute inset-y-0 right-0 flex items-center px-3.5 text-slate-500 hover:text-slate-300"
                    tabIndex={-1}
                    aria-label={showPassword ? "Hide password" : "Show password"}
                  >
                    {showPassword ? <EyeOff className="h-5 w-5" /> : <Eye className="h-5 w-5" />}
                  </button>
                </div>
              </div>

              <button
                type="submit"
                className="mkt-btn-primary w-full"
                disabled={mutation.isPending}
              >
                {mutation.isPending ? (
                  <>
                    <Loader2 className="h-5 w-5 animate-spin" />
                    Creating workspace…
                  </>
                ) : (
                  <>
                    Create workspace
                    <ArrowRight className="h-5 w-5" />
                  </>
                )}
              </button>
            </form>

            <p className="mt-6 text-center text-base text-slate-400">
              Already have an account?{" "}
              <Link to="/login" className="font-semibold text-teal-400 hover:text-teal-300">
                Sign in
              </Link>
            </p>
            <p className="mt-3 text-center text-sm text-slate-500">
              By signing up you agree to our{" "}
              <Link to="/terms" className="underline hover:text-slate-300">
                Terms
              </Link>{" "}
              and{" "}
              <Link to="/privacy" className="underline hover:text-slate-300">
                Privacy Policy
              </Link>
              .
            </p>
          </div>
        </div>
      </section>
    </MarketingLayout>
  );
}
