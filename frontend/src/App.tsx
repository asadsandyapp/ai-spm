import { BrowserRouter, Navigate, Outlet, Route, Routes } from "react-router-dom";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { ProtectedRoute } from "@/components/ProtectedRoute";
import { MainLayout } from "@/components/layout/MainLayout";
import { LoginPage } from "@/pages/LoginPage";
import { SignupPage } from "@/pages/SignupPage";
import { VerifyEmailPage } from "@/pages/VerifyEmailPage";
import { DashboardPage } from "@/pages/DashboardPage";
import { AgentsPage } from "@/pages/AgentsPage";
import { DownloadAgentPage } from "@/pages/DownloadAgentPage";
import { PoliciesPage } from "@/pages/PoliciesPage";
import { AuditPage } from "@/pages/AuditPage";
import { TenantsPage } from "@/pages/platform/TenantsPage";
import { TenantDetailPage } from "@/pages/platform/TenantDetailPage";
import { LeadsPage } from "@/pages/platform/LeadsPage";
import { SettingsPage } from "@/pages/SettingsPage";
import { AccountPage } from "@/pages/AccountPage";
import { ThreatsPage } from "@/pages/ThreatsPage";
import { ReportsPage } from "@/pages/ReportsPage";
import { NotFoundPage } from "@/pages/NotFoundPage";
import { LandingPage } from "@/pages/marketing/LandingPage";
import { PricingPage } from "@/pages/marketing/PricingPage";
import { ProductPage } from "@/pages/marketing/ProductPage";
import { SecurityPage } from "@/pages/marketing/SecurityPage";
import { ContactSalesPage } from "@/pages/marketing/ContactSalesPage";
import { LegalPage } from "@/pages/marketing/LegalPage";
import { PlansPage } from "@/pages/onboarding/PlansPage";
import { BillingPage } from "@/pages/billing/BillingPage";
import { BillingSuccessPage } from "@/pages/billing/BillingSuccessPage";

export function App() {
  return (
    <ErrorBoundary>
      <BrowserRouter>
        <Routes>
        <Route path="/" element={<LandingPage />} />
        <Route path="/pricing" element={<PricingPage />} />
        <Route path="/product" element={<ProductPage />} />
        <Route path="/security" element={<SecurityPage />} />
        <Route path="/contact-sales" element={<ContactSalesPage />} />
        <Route path="/contact" element={<Navigate to="/contact-sales" replace />} />
        <Route path="/terms" element={<LegalPage kind="terms" />} />
        <Route path="/privacy" element={<LegalPage kind="privacy" />} />
        <Route path="/dpa" element={<LegalPage kind="dpa" />} />

        <Route path="/signup" element={<SignupPage />} />
        <Route path="/verify" element={<VerifyEmailPage />} />
        <Route path="/verify-email" element={<VerifyEmailPage />} />

        <Route path="/login" element={<LoginPage />} />
        <Route
          path="/platform/login"
          element={<Navigate to="/login" replace />}
        />

        <Route
          element={
            <ProtectedRoute scope="admin" allowUnpaid>
              <Outlet />
            </ProtectedRoute>
          }
        >
          <Route path="/onboarding/plans" element={<PlansPage />} />
          <Route path="/billing/success" element={<BillingSuccessPage />} />
          <Route
            path="/billing/cancel"
            element={<Navigate to="/pricing?checkout=canceled" replace />}
          />
        </Route>

        <Route
          element={
            <ProtectedRoute scope="admin">
              <MainLayout scope="admin" />
            </ProtectedRoute>
          }
        >
          <Route path="/dashboard" element={<DashboardPage />} />
          <Route path="/threats" element={<ThreatsPage />} />
          <Route path="/reports" element={<ReportsPage />} />
          <Route path="/agents" element={<AgentsPage />} />
          <Route path="/agents/download" element={<DownloadAgentPage />} />
          <Route path="/policies" element={<PoliciesPage />} />
          <Route path="/audit" element={<AuditPage />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="/account" element={<AccountPage scope="admin" />} />
          <Route path="/billing" element={<BillingPage />} />
        </Route>

        <Route
          element={
            <ProtectedRoute scope="platform">
              <MainLayout scope="platform" />
            </ProtectedRoute>
          }
        >
          <Route path="/platform/tenants" element={<TenantsPage />} />
          <Route path="/platform/tenants/:orgId" element={<TenantDetailPage />} />
          <Route path="/platform/leads" element={<LeadsPage />} />
          <Route
            path="/platform/account"
            element={<AccountPage scope="platform" />}
          />
        </Route>

        <Route path="/platform" element={<Navigate to="/platform/tenants" replace />} />
        <Route path="*" element={<NotFoundPage />} />
        </Routes>
      </BrowserRouter>
    </ErrorBoundary>
  );
}
