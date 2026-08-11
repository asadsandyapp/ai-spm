import { useEffect, useState, type ReactNode } from "react";
import { Link, useLocation } from "react-router-dom";
import { Menu, ShieldCheck, X } from "lucide-react";
import { cn } from "@/lib/utils";

const NAV_LINKS = [
  { label: "Product", to: "/product" },
  { label: "Pricing", to: "/pricing" },
  { label: "Security", to: "/security" },
  { label: "Contact sales", to: "/contact-sales" },
] as const;

interface MarketingLayoutProps {
  children: ReactNode;
}

export function MarketingLayout({ children }: MarketingLayoutProps) {
  const [scrolled, setScrolled] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const location = useLocation();

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 12);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  useEffect(() => {
    window.scrollTo(0, 0);
    setMobileOpen(false);
  }, [location.pathname]);

  return (
    <div className="marketing-root relative min-h-full">
      <div className="mkt-atmosphere pointer-events-none fixed inset-0 z-0 opacity-30" aria-hidden />

      <header
        className={cn(
          "fixed inset-x-0 top-0 z-50 transition-all duration-300",
          scrolled
            ? "border-b border-white/10 bg-marketing-ink/90 shadow-[0_8px_32px_-12px_rgba(0,0,0,0.7)] backdrop-blur-xl"
            : "border-b border-white/[0.06] bg-marketing-ink/70 backdrop-blur-md",
        )}
      >
        <div className="mkt-shell flex h-[5rem] items-center justify-between">
          <Link to="/" className="group flex items-center gap-3.5">
            <div className="grid h-11 w-11 place-items-center rounded-xl bg-gradient-to-br from-teal-400/30 to-teal-600/10 ring-1 ring-teal-400/40 transition group-hover:ring-teal-400/60">
              <ShieldCheck className="h-6 w-6 text-teal-400" strokeWidth={2.2} />
            </div>
            <span className="font-display text-2xl font-bold tracking-tight text-white">
              AI-SPM
            </span>
          </Link>

          <nav className="hidden items-center gap-1 lg:flex">
            {NAV_LINKS.map((link) => (
              <Link
                key={link.to}
                to={link.to}
                className={cn(
                  "rounded-lg px-4 py-2.5 text-base font-medium transition-colors",
                  location.pathname === link.to
                    ? "bg-white/8 text-teal-400"
                    : "text-slate-300 hover:bg-white/[0.05] hover:text-white",
                )}
              >
                {link.label}
              </Link>
            ))}
          </nav>

          <div className="flex items-center gap-4">
            <Link
              to="/login"
              className="hidden text-base font-medium text-slate-300 transition-colors hover:text-white sm:inline"
            >
              Login
            </Link>
            <Link to="/signup" className="mkt-btn-primary !px-5 !py-2.5 !text-[15px]">
              Get started
            </Link>
            <button
              type="button"
              className="grid h-11 w-11 place-items-center rounded-xl text-slate-200 ring-1 ring-white/15 lg:hidden"
              onClick={() => setMobileOpen((v) => !v)}
              aria-label="Toggle menu"
            >
              {mobileOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
            </button>
          </div>
        </div>

        {mobileOpen && (
          <div className="border-t border-white/10 bg-marketing-ink/95 px-6 py-4 backdrop-blur-xl lg:hidden">
            <div className="flex flex-col gap-1">
              {NAV_LINKS.map((link) => (
                <Link
                  key={link.to}
                  to={link.to}
                  className={cn(
                    "rounded-lg px-3 py-3 text-base font-medium",
                    location.pathname === link.to
                      ? "bg-white/5 text-teal-400"
                      : "text-slate-200",
                  )}
                >
                  {link.label}
                </Link>
              ))}
              <Link to="/login" className="rounded-lg px-3 py-3 text-base font-medium text-slate-200">
                Login
              </Link>
            </div>
          </div>
        )}
      </header>

      <main className="relative z-10">{children}</main>

      <footer className="relative z-10 border-t border-white/10 bg-[#080d18]">
        <div className="mkt-shell py-14 sm:py-16">
          <div className="grid gap-12 sm:grid-cols-2 lg:grid-cols-[1.5fr_repeat(3,1fr)]">
            <div className="max-w-lg">
              <div className="flex items-center gap-3.5">
                <div className="grid h-11 w-11 place-items-center rounded-xl bg-teal-400/10 ring-1 ring-teal-400/30">
                  <ShieldCheck className="h-6 w-6 text-teal-400" strokeWidth={2.2} />
                </div>
                <span className="font-display text-2xl font-bold text-white">AI-SPM</span>
              </div>
              <p className="mt-5 text-lg leading-relaxed text-slate-400">
                Sensitive company data never reaches ChatGPT, Claude, or Gemini unprotected.
              </p>
            </div>

            {(
              [
                {
                  title: "Product",
                  links: [
                    { to: "/product", label: "Features" },
                    { to: "/pricing", label: "Pricing" },
                    { to: "/security", label: "Security" },
                  ],
                },
                {
                  title: "Legal",
                  links: [
                    { to: "/terms", label: "Terms" },
                    { to: "/privacy", label: "Privacy" },
                    { to: "/dpa", label: "DPA" },
                  ],
                },
                {
                  title: "Contact",
                  links: [
                    { to: "/contact-sales", label: "Contact sales" },
                    { to: "/signup", label: "Get started" },
                    { to: "/login", label: "Login" },
                  ],
                },
              ] as const
            ).map((col) => (
              <div key={col.title} className="space-y-3.5">
                <p className="text-sm font-semibold uppercase tracking-wider text-slate-500">
                  {col.title}
                </p>
                {col.links.map((l) => (
                  <Link
                    key={l.to}
                    to={l.to}
                    className="block text-[17px] text-slate-300 transition hover:text-teal-400"
                  >
                    {l.label}
                  </Link>
                ))}
              </div>
            ))}
          </div>

          <div className="mkt-divider mt-10" />
          <p className="pt-6 text-sm text-slate-600">
            © {new Date().getFullYear()} AI-SPM. Proprietary — all rights reserved.
          </p>
        </div>
      </footer>
    </div>
  );
}
