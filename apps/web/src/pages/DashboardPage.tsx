import { useQuery } from "@tanstack/react-query";
import { Activity, UserPlus, Users } from "lucide-react";
import { Link } from "react-router";
import { api } from "../api/client";
import { useAuth } from "../auth/AuthProvider";
import type { AuditEvent, Invitation, Member } from "../types";

export function DashboardPage() {
  const { me } = useAuth();
  const organization = me?.organizations[0];
  const members = useQuery({
    queryKey: ["members", organization?.id],
    enabled: Boolean(organization),
    queryFn: () =>
      api<Member[]>(`/api/v1/organizations/${organization!.id}/members`),
  });
  const invitations = useQuery({
    queryKey: ["invitations", organization?.id],
    enabled: Boolean(
      organization && ["owner", "admin"].includes(organization.role),
    ),
    queryFn: () =>
      api<Invitation[]>(
        `/api/v1/organizations/${organization!.id}/invitations`,
      ),
  });
  const audit = useQuery({
    queryKey: ["audit", organization?.id],
    enabled: Boolean(
      organization && ["owner", "admin", "auditor"].includes(organization.role),
    ),
    queryFn: () =>
      api<AuditEvent[]>(
        `/api/v1/organizations/${organization!.id}/audit-events`,
      ),
  });
  if (!organization)
    return (
      <section className="card text-center">
        <h1 className="text-3xl font-bold">Create your first organization</h1>
        <p className="my-4 text-slate-400">
          CloudOps data is always organization-scoped.
        </p>
        <Link className="button" to="/organizations/new">
          Create organization
        </Link>
      </section>
    );
  const active =
    members.data?.filter((item) => item.status === "active").length ?? 0;
  const suspended =
    members.data?.filter((item) => item.status === "suspended").length ?? 0;
  const pending =
    invitations.data?.filter((item) => item.status === "pending").length ?? 0;
  return (
    <div className="grid gap-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-sm font-semibold uppercase tracking-wider text-blue-400">
            Stage 1 administration
          </p>
          <h1 className="text-3xl font-extrabold">{organization.name}</h1>
          <p className="text-slate-400">
            Your role: {organization.role.replace("_", " ")}
          </p>
        </div>
        <div className="flex gap-3">
          <Link className="button" to="/members/invite">
            <UserPlus size={18} />
            Invite member
          </Link>
          <Link className="button-secondary" to="/organizations/new">
            Create organization
          </Link>
        </div>
      </div>
      {members.isLoading ? (
        <p aria-live="polite">Loading dashboard…</p>
      ) : members.isError ? (
        <p role="alert" className="text-red-400">
          Unable to load dashboard.
        </p>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {[
            ["Total members", members.data?.length ?? 0],
            ["Active members", active],
            ["Suspended", suspended],
            ["Pending invitations", pending],
          ].map(([label, value]) => (
            <article className="card" key={label}>
              <p className="text-sm text-slate-400">{label}</p>
              <p className="mt-2 text-3xl font-extrabold">{value}</p>
            </article>
          ))}
        </div>
      )}
      <section className="card">
        <div className="mb-4 flex items-center gap-2">
          <Activity className="text-blue-400" />
          <h2 className="text-xl font-bold">Recent activity</h2>
        </div>
        {audit.isLoading && <p>Loading activity…</p>}
        {audit.data?.length === 0 && (
          <p className="text-slate-400">No recent activity.</p>
        )}
        <ol className="grid gap-3">
          {audit.data?.slice(0, 8).map((item) => (
            <li
              className="flex justify-between border-b border-border pb-3"
              key={item.id}
            >
              <span>{item.event_type.replaceAll(".", " ")}</span>
              <time className="text-sm text-slate-400">
                {new Date(item.created_at).toLocaleString()}
              </time>
            </li>
          ))}
        </ol>
        <Link
          className="mt-5 inline-flex items-center gap-2 text-blue-400"
          to="/members"
        >
          <Users size={18} />
          View members
        </Link>
      </section>
    </div>
  );
}
