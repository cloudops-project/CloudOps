import { Navigate, Route, Routes } from "react-router-dom";
import { AppShell } from "./components/AppShell";
import { ProtectedRoute } from "./components/ProtectedRoute";
import { AcceptInvitationPage } from "./pages/AcceptInvitationPage";
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
import { ProfilePage } from "./pages/ProfilePage";
import { RegisterPage } from "./pages/RegisterPage";
import { NotFoundPage, UnauthorizedPage } from "./pages/StatusPages";
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
