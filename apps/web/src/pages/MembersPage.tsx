import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router";
import { api } from "../api/client";
import { useAuth } from "../auth/AuthProvider";
import type { Member, Role } from "../types";

const roles: Role[] = [
  "owner",
  "admin",
  "security_analyst",
  "cloud_engineer",
  "auditor",
  "viewer",
];
export function MembersPage() {
  const { me } = useAuth();
  const org = me?.organizations[0];
  const queryClient = useQueryClient();
  const canManage = Boolean(org && ["owner", "admin"].includes(org.role));
  const query = useQuery({
    queryKey: ["members", org?.id],
    enabled: Boolean(org),
    queryFn: () => api<Member[]>(`/api/v1/organizations/${org!.id}/members`),
  });
  const mutate = useMutation({
    mutationFn: ({
      member,
      body,
      action,
    }: {
      member: Member;
      body?: object;
      action: "role" | "status" | "remove";
    }) =>
      api(
        `/api/v1/organizations/${org!.id}/members/${member.id}${action === "remove" ? "" : `/${action}`}`,
        {
          method: action === "remove" ? "DELETE" : "PATCH",
          body: body ? JSON.stringify(body) : undefined,
        },
      ),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["members", org?.id] }),
  });
  if (!org) return <p>No organization selected.</p>;
  return (
    <section>
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">Organization members</h1>
          <p className="text-slate-400">Roles and access for {org.name}</p>
        </div>
        {canManage && (
          <Link className="button" to="/members/invite">
            Invite member
          </Link>
        )}
      </div>
      {query.isLoading && <p aria-live="polite">Loading members…</p>}
      {query.isError && (
        <p role="alert" className="text-red-400">
          Unable to load members.
        </p>
      )}
      <div className="grid gap-3">
        {query.data?.map((member) => (
          <article
            className="card flex flex-col justify-between gap-4 md:flex-row md:items-center"
            key={member.id}
          >
            <div>
              <h2 className="font-bold">{member.full_name}</h2>
              <p className="text-sm text-slate-400">
                {member.email} · {member.status}
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              {canManage ? (
                <select
                  aria-label={`Role for ${member.full_name}`}
                  className="input w-auto"
                  value={member.role}
                  onChange={(event) =>
                    mutate.mutate({
                      member,
                      action: "role",
                      body: { role: event.target.value },
                    })
                  }
                >
                  {roles
                    .filter((role) => org.role === "owner" || role !== "owner")
                    .map((role) => (
                      <option key={role}>{role}</option>
                    ))}
                </select>
              ) : (
                <span>{member.role}</span>
              )}
              {canManage && member.role !== "owner" && (
                <>
                  <button
                    className="button-secondary"
                    onClick={() =>
                      mutate.mutate({
                        member,
                        action: "status",
                        body: {
                          status:
                            member.status === "active" ? "suspended" : "active",
                        },
                      })
                    }
                  >
                    {member.status === "active" ? "Suspend" : "Reactivate"}
                  </button>
                  <button
                    className="button bg-critical hover:bg-red-700"
                    onClick={() => mutate.mutate({ member, action: "remove" })}
                  >
                    Remove
                  </button>
                </>
              )}
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}
