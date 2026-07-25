import { Navigate, Route, Routes } from "react-router";
import { AppShell } from "./components/AppShell";
import { ProtectedRoute } from "./components/ProtectedRoute";
import { AcceptInvitationPage } from "./pages/AcceptInvitationPage";
import { AIAssistantPage } from "./pages/AIAssistantPage";
import { AuditPage } from "./pages/AuditPage";
import {
  AddAWSAccountPage,
  AWSAccountDetailsPage,
  AWSAccountsPage,
  ConnectionFailurePage,
  ConnectionValidationPage,
  DisconnectConfirmationPage,
} from "./pages/AWSAccountsPages";
import { CreateOrganizationPage } from "./pages/CreateOrganizationPage";
import { DashboardPage } from "./pages/DashboardPage";
import { InviteMemberPage } from "./pages/InviteMemberPage";
import { LoginPage } from "./pages/LoginPage";
import { MembersPage } from "./pages/MembersPage";
import { NotificationsPage } from "./pages/NotificationsPage";
import { ProfilePage } from "./pages/ProfilePage";
import { RegisterPage } from "./pages/RegisterPage";
import { RemediationsPage } from "./pages/RemediationsPage";
import { RiskPage } from "./pages/RiskPage";
import { SchedulesPage } from "./pages/SchedulesPage";
import { SecurityDashboardPage } from "./pages/SecurityDashboardPage";
import { NotFoundPage, UnauthorizedPage } from "./pages/StatusPages";
import {
  ComplianceAssessmentPage,
  ComplianceAssessmentsPage,
  ComplianceControlPage,
  ComplianceFrameworkPage,
  CompliancePage,
} from "./pages/CompliancePage";
import {
  EvaluationJobsPage,
  FindingDetailsPage,
  FindingsDashboardPage,
  FindingsPage,
  RuleCatalogPage,
} from "./pages/FindingsPages";
import {
  AssetDetailsPage,
  AssetsPage,
  DiscoveryJobsPage,
} from "./pages/AssetsPages";

export function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />
      <Route element={<ProtectedRoute />}>
        <Route path="/invitations/accept" element={<AcceptInvitationPage />} />
        <Route element={<AppShell />}>
          <Route path="/dashboard" element={<DashboardPage />} />
          <Route
            path="/organizations/new"
            element={<CreateOrganizationPage />}
          />
          <Route path="/members" element={<MembersPage />} />
          <Route path="/members/invite" element={<InviteMemberPage />} />
          <Route path="/profile" element={<ProfilePage />} />
          <Route path="/assets" element={<AssetsPage />} />
          <Route path="/assets/:assetId" element={<AssetDetailsPage />} />
          <Route path="/discovery/jobs" element={<DiscoveryJobsPage />} />
          <Route path="/security" element={<FindingsDashboardPage />} />
          <Route path="/findings" element={<FindingsPage />} />
          <Route path="/findings/:findingId" element={<FindingDetailsPage />} />
          <Route path="/rules" element={<RuleCatalogPage />} />
          <Route path="/evaluations" element={<EvaluationJobsPage />} />
          <Route path="/compliance" element={<CompliancePage />} />
          <Route path="/risk" element={<RiskPage />} />
          <Route path="/notifications" element={<NotificationsPage />} />
          <Route path="/remediations" element={<RemediationsPage />} />
          <Route path="/schedules" element={<SchedulesPage />} />
          <Route path="/audit" element={<AuditPage />} />
          <Route
            path="/security-dashboard"
            element={<SecurityDashboardPage />}
          />
          <Route path="/ai" element={<AIAssistantPage />} />
          <Route
            path="/compliance/frameworks/:frameworkKey"
            element={<ComplianceFrameworkPage />}
          />
          <Route
            path="/compliance/controls/:controlId"
            element={<ComplianceControlPage />}
          />
          <Route
            path="/compliance/assessments"
            element={<ComplianceAssessmentsPage />}
          />
          <Route
            path="/compliance/assessments/:assessmentId"
            element={<ComplianceAssessmentPage />}
          />
          <Route path="/aws/accounts" element={<AWSAccountsPage />} />
          <Route path="/aws/accounts/new" element={<AddAWSAccountPage />} />
          <Route
            path="/aws/accounts/:accountId"
            element={<AWSAccountDetailsPage />}
          />
          <Route
            path="/aws/accounts/:accountId/validate"
            element={<ConnectionValidationPage />}
          />
          <Route
            path="/aws/accounts/:accountId/failure"
            element={<ConnectionFailurePage />}
          />
          <Route
            path="/aws/accounts/:accountId/disconnect"
            element={<DisconnectConfirmationPage />}
          />
        </Route>
      </Route>
      <Route path="/unauthorized" element={<UnauthorizedPage />} />
      <Route path="/" element={<Navigate to="/dashboard" replace />} />
      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  );
}
