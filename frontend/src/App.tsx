import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { ProtectedRoute } from "@/components/ProtectedRoute";
import { MainLayout } from "@/components/layout/MainLayout";
import { LoginPage } from "@/pages/LoginPage";
import { DashboardPage } from "@/pages/DashboardPage";
import { AgentsPage } from "@/pages/AgentsPage";
import { DownloadAgentPage } from "@/pages/DownloadAgentPage";
import { PoliciesPage } from "@/pages/PoliciesPage";
import { AuditPage } from "@/pages/AuditPage";
import { PlatformLoginPage } from "@/pages/platform/PlatformLoginPage";
import { TenantsPage } from "@/pages/platform/TenantsPage";
import { SettingsPage } from "@/pages/SettingsPage";
import { ThreatsPage } from "@/pages/ThreatsPage";
import { ReportsPage } from "@/pages/ReportsPage";
import { NotFoundPage } from "@/pages/NotFoundPage";

export function App() {
  return (
    <BrowserRouter>
      <Routes>
        {/* Public auth routes */}
        <Route path="/login" element={<LoginPage />} />
        <Route path="/platform/login" element={<PlatformLoginPage />} />

        {/* Tenant admin console */}
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
        </Route>

        {/* Platform operations console */}
        <Route
          element={
            <ProtectedRoute scope="platform">
              <MainLayout scope="platform" />
            </ProtectedRoute>
          }
        >
          <Route path="/platform/tenants" element={<TenantsPage />} />
        </Route>

        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        <Route path="/platform" element={<Navigate to="/platform/tenants" replace />} />
        <Route path="*" element={<NotFoundPage />} />
      </Routes>
    </BrowserRouter>
  );
}
