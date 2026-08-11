import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { AlertCircle, CheckCircle2, Loader2, Shield } from "lucide-react";
import { MarketingLayout } from "@/components/marketing/MarketingLayout";
import { ApiError, publicApi } from "@/lib/api";

interface ContactSalesForm {
  company: string;
  contact_name: string;
  email: string;
  phone: string;
  estimated_agents: string;
  message: string;
}

export function ContactSalesPage() {
  const [form, setForm] = useState<ContactSalesForm>({
    company: "",
    contact_name: "",
    email: "",
    phone: "",
    estimated_agents: "",
    message: "",
  });

  const mutation = useMutation({
    mutationFn: (body: ContactSalesForm) =>
      publicApi.contactSales({
        ...body,
        estimated_agents: Number(body.estimated_agents) || 0,
      }),
  });

  const errorMessage =
    mutation.error instanceof ApiError
      ? mutation.error.detail
      : mutation.error
        ? "Unable to submit your request. Please try again."
        : null;

  function handleChange(
    e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>,
  ) {
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
              "radial-gradient(48rem 28rem at 72% 0%, rgba(45,212,191,0.12), transparent 55%)",
          }}
        />
        <div className="mkt-shell relative grid gap-12 py-16 lg:grid-cols-[1fr_1.2fr] lg:gap-16 lg:py-20">
          <div>
            <p className="mkt-eyebrow">Contact sales</p>
            <h1 className="mkt-h1 mt-4">Let&apos;s scope your deployment.</h1>
            <p className="mkt-lead mt-6 text-slate-200">
              Tell us about fleet size and requirements. We follow up within one business day with
              a custom Enterprise quote.
            </p>
            <ul className="mt-10 space-y-5 text-lg text-slate-300">
              {[
                "Unlimited agents & custom quotas",
                "Priority deployment support",
                "24/7 priority support with SLA",
              ].map((item) => (
                <li key={item} className="flex items-start gap-3.5">
                  <Shield className="mt-1 h-5 w-5 shrink-0 text-teal-400" />
                  {item}
                </li>
              ))}
            </ul>
          </div>

          <div className="mkt-panel p-7 sm:p-9">
            {mutation.isSuccess ? (
              <div className="py-12 text-center">
                <CheckCircle2 className="mx-auto h-16 w-16 text-teal-400" />
                <h2 className="mt-6 font-display text-3xl font-semibold text-white">
                  Request received
                </h2>
                <p className="mt-4 text-lg text-slate-400">
                  We&apos;ll be in touch shortly. Meanwhile you can{" "}
                  <Link to="/signup" className="text-teal-400 hover:text-teal-300">
                    create a workspace
                  </Link>{" "}
                  on Starter or Professional.
                </p>
              </div>
            ) : (
              <form onSubmit={handleSubmit} className="space-y-5">
                {errorMessage && (
                  <div className="flex items-start gap-2.5 rounded-xl border border-rose-500/30 bg-rose-500/10 px-4 py-3.5 text-[17px] text-rose-200">
                    <AlertCircle className="mt-0.5 h-5 w-5 shrink-0" />
                    <span>{errorMessage}</span>
                  </div>
                )}

                <div className="grid gap-5 sm:grid-cols-2">
                  <div className="sm:col-span-2">
                    <label htmlFor="company" className="mkt-label">
                      Company
                    </label>
                    <input
                      id="company"
                      name="company"
                      required
                      value={form.company}
                      onChange={handleChange}
                      className="mkt-input"
                    />
                  </div>
                  <div>
                    <label htmlFor="contact_name" className="mkt-label">
                      Contact name
                    </label>
                    <input
                      id="contact_name"
                      name="contact_name"
                      required
                      value={form.contact_name}
                      onChange={handleChange}
                      className="mkt-input"
                    />
                  </div>
                  <div>
                    <label htmlFor="email" className="mkt-label">
                      Work email
                    </label>
                    <input
                      id="email"
                      name="email"
                      type="email"
                      required
                      value={form.email}
                      onChange={handleChange}
                      className="mkt-input"
                    />
                  </div>
                  <div>
                    <label htmlFor="phone" className="mkt-label">
                      Phone
                    </label>
                    <input
                      id="phone"
                      name="phone"
                      value={form.phone}
                      onChange={handleChange}
                      className="mkt-input"
                    />
                  </div>
                  <div>
                    <label htmlFor="estimated_agents" className="mkt-label">
                      Estimated agents
                    </label>
                    <input
                      id="estimated_agents"
                      name="estimated_agents"
                      inputMode="numeric"
                      placeholder="e.g. 500"
                      value={form.estimated_agents}
                      onChange={handleChange}
                      className="mkt-input"
                    />
                  </div>
                  <div className="sm:col-span-2">
                    <label htmlFor="message" className="mkt-label">
                      Message
                    </label>
                    <textarea
                      id="message"
                      name="message"
                      rows={4}
                      placeholder="Deployment timeline, SSO needs, MSP requirements…"
                      value={form.message}
                      onChange={handleChange}
                      className="mkt-input resize-y"
                    />
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
                      Submitting…
                    </>
                  ) : (
                    "Submit inquiry"
                  )}
                </button>
              </form>
            )}
          </div>
        </div>
      </section>
    </MarketingLayout>
  );
}
