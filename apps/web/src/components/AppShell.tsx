import {
  Bell,
  Building2,
  CalendarClock,
  ClipboardList,
  Cloud,
  Database,
  Gauge,
  LayoutDashboard,
  LogOut,
  ShieldAlert,
  Scale,
  ShieldCheck,
  Sparkles,
  Users,
  UserRound,
  Wrench,
} from "lucide-react";
import { Link, Outlet } from "react-router";
import { useAuth } from "../auth/AuthProvider";

export function AppShell() {
  const { me, signOut } = useAuth();
  const organizationRole = me?.organizations[0]?.role;
  return (
    <div className="min-h-screen bg-canvas md:grid md:grid-cols-[240px_1fr]">
      <aside className="border-b border-border bg-sidebar p-5 md:min-h-screen md:border-b-0 md:border-r">
        <Link
          to="/dashboard"
          className="flex items-center gap-3 text-xl font-extrabold"
        >
          <Building2 className="text-blue-400" />
          CloudOps
        </Link>
        <nav className="mt-8 grid gap-2" aria-label="Primary">
          {organizationRole && (
            <Link
              className="flex items-center gap-3 rounded-button px-3 hover:bg-slate-800"
              to="/aws/accounts"
            >
              <Cloud />
              AWS Accounts
            </Link>
          )}
          <Link
            className="flex items-center gap-3 rounded-button px-3 hover:bg-slate-800"
            to="/assets"
          >
            <Database />
            Assets
          </Link>
          <Link
            className="flex items-center gap-3 rounded-button px-3 hover:bg-slate-800"
            to="/security"
          >
            <ShieldAlert />
            Security
          </Link>
          <Link
            className="flex items-center gap-3 rounded-button px-3 hover:bg-slate-800"
            to="/security-dashboard"
          >
            <ShieldCheck />
            Security Posture
          </Link>
          <Link
            className="flex items-center gap-3 rounded-button px-3 hover:bg-slate-800"
            to="/compliance"
          >
            <Scale />
            Compliance
          </Link>
          <Link
            className="flex items-center gap-3 rounded-button px-3 hover:bg-slate-800"
            to="/risk"
          >
            <Gauge />
            Risk
          </Link>
          <Link
            className="flex items-center gap-3 rounded-button px-3 hover:bg-slate-800"
            to="/ai"
          >
            <Sparkles />
            AI Assistant
          </Link>
          <Link
            className="flex items-center gap-3 rounded-button px-3 hover:bg-slate-800"
            to="/notifications"
          >
            <Bell />
            Notifications
          </Link>
          <Link
            className="flex items-center gap-3 rounded-button px-3 hover:bg-slate-800"
            to="/remediations"
          >
            <Wrench />
            Remediation
          </Link>
          <Link
            className="flex items-center gap-3 rounded-button px-3 hover:bg-slate-800"
            to="/schedules"
          >
            <CalendarClock />
            Schedules
          </Link>
          {organizationRole &&
            ["owner", "admin", "auditor"].includes(organizationRole) && (
              <Link
                className="flex items-center gap-3 rounded-button px-3 hover:bg-slate-800"
                to="/audit"
              >
                <ClipboardList />
                Audit log
              </Link>
            )}
          <Link
            className="flex items-center gap-3 rounded-button px-3 hover:bg-slate-800"
            to="/dashboard"
          >
            <LayoutDashboard />
            Dashboard
          </Link>
          <Link
            className="flex items-center gap-3 rounded-button px-3 hover:bg-slate-800"
            to="/members"
          >
            <Users />
            Members
          </Link>
          <Link
            className="flex items-center gap-3 rounded-button px-3 hover:bg-slate-800"
            to="/profile"
          >
            <UserRound />
            Profile
          </Link>
        </nav>
      </aside>
      <div>
        <header className="flex min-h-16 items-center justify-between border-b border-border bg-surface px-5">
          <span className="text-sm text-slate-300">{me?.user.email}</span>
          <button className="button-secondary" onClick={() => void signOut()}>
            <LogOut size={18} />
            Logout
          </button>
        </header>
        <main className="mx-auto max-w-7xl p-5 md:p-8">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
