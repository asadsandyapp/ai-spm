import { useState } from "react";
import { AlertCircle, ArrowRight, Eye, EyeOff, Loader2 } from "lucide-react";

interface CredentialsFormProps {
  onSubmit: (email: string, password: string) => void;
  pending: boolean;
  error?: string | null;
  defaultEmail?: string;
  emailLabel?: string;
  submitLabel?: string;
}

export function CredentialsForm({
  onSubmit,
  pending,
  error,
  defaultEmail = "",
  emailLabel = "Work email",
  submitLabel = "Sign in",
}: CredentialsFormProps) {
  const [email, setEmail] = useState(defaultEmail);
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!email || !password || pending) return;
    onSubmit(email.trim(), password);
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-5" noValidate>
      {error && (
        <div className="flex items-start gap-2.5 rounded-xl border border-rose-200 bg-rose-50 px-4 py-3.5 text-[14px] leading-relaxed text-rose-700">
          <AlertCircle className="mt-0.5 h-4.5 w-4.5 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      <div>
        <label htmlFor="email" className="label text-[13px] text-ink-600">
          {emailLabel}
        </label>
        <input
          id="email"
          type="email"
          autoComplete="username"
          className="input mt-1.5 py-3 text-[15px] shadow-sm transition-shadow focus:shadow-md"
          placeholder="you@company.com"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
          autoFocus
        />
      </div>

      <div>
        <label htmlFor="password" className="label text-[13px] text-ink-600">
          Password
        </label>
        <div className="relative mt-1.5">
          <input
            id="password"
            type={showPassword ? "text" : "password"}
            autoComplete="current-password"
            className="input py-3 pr-11 text-[15px] shadow-sm transition-shadow focus:shadow-md"
            placeholder="Enter your password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
          <button
            type="button"
            onClick={() => setShowPassword((s) => !s)}
            className="absolute inset-y-0 right-0 flex items-center px-3.5 text-ink-400 transition-colors hover:text-ink-700"
            tabIndex={-1}
            aria-label={showPassword ? "Hide password" : "Show password"}
          >
            {showPassword ? (
              <EyeOff className="h-4.5 w-4.5" />
            ) : (
              <Eye className="h-4.5 w-4.5" />
            )}
          </button>
        </div>
      </div>

      <button
        type="submit"
        className="btn-primary mt-1 w-full py-3.5 text-[15px] font-semibold shadow-md shadow-brand-600/20 transition hover:shadow-lg hover:shadow-brand-600/25"
        disabled={pending || !email || !password}
      >
        {pending ? (
          <>
            <Loader2 className="h-5 w-5 animate-spin" />
            Signing in…
          </>
        ) : (
          <>
            {submitLabel}
            <ArrowRight className="h-4.5 w-4.5" />
          </>
        )}
      </button>
    </form>
  );
}
