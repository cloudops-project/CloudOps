import { useState } from "react";
import { useForm } from "react-hook-form";
import { useNavigate } from "react-router";
import { api } from "../api/client";
import { useAuth } from "../auth/AuthProvider";
import { Field } from "../components/AuthCard";
import type { Invitation, Role } from "../types";

export function InviteMemberPage() {
  const { me } = useAuth();
  const org = me?.organizations[0];
  const navigate = useNavigate();
  const [error, setError] = useState("");
  const [token, setToken] = useState("");
  const {
    register,
    handleSubmit,
    formState: { isSubmitting },
  } = useForm<{ email: string; role: Role }>({
    defaultValues: { role: "viewer" },
  });
  if (!org || !["owner", "admin"].includes(org.role))
    return <p role="alert">You do not have permission to invite members.</p>;
  return (
    <section className="card max-w-xl">
      <h1 className="text-3xl font-bold">Invite member</h1>
      <p className="mt-2 text-slate-400">
        Production email delivery is deferred. Development returns a one-time
        token, and the local demo stack can also send the invitation to Mailpit.
      </p>
      <form
        className="mt-6 grid gap-4"
        onSubmit={handleSubmit(async (values) => {
          try {
            const invite = await api<Invitation>(
              `/api/v1/organizations/${org.id}/invitations`,
              { method: "POST", body: JSON.stringify(values) },
            );
            if (invite.development_token) setToken(invite.development_token);
            else navigate("/members");
          } catch (e) {
            setError(e instanceof Error ? e.message : "Invitation failed.");
          }
        })}
      >
        <Field label="Email" type="email" required {...register("email")} />
        <label>
          <span className="label">Role</span>
          <select className="input" {...register("role")}>
            {(
              [
                "admin",
                "security_analyst",
                "cloud_engineer",
                "auditor",
                "viewer",
              ] as Role[]
            ).map((role) => (
              <option key={role} value={role}>
                {role.replace("_", " ")}
              </option>
            ))}
          </select>
        </label>
        {error && (
          <p role="alert" className="text-red-400">
            {error}
          </p>
        )}
        <button className="button" disabled={isSubmitting}>
          Send invitation
        </button>
      </form>
      {token && (
        <div className="mt-5 rounded-button border border-warning bg-amber-500/10 p-4">
          <p className="font-semibold">Development invitation link</p>
          <p className="mt-1 text-sm text-slate-400">
            Built from the origin you are currently using (
            {window.location.origin}), so it works whether this is localhost or
            the temporary tunnel URL. Send this exact link to the invited guest.
          </p>
          <code className="mt-2 block break-all text-sm">
            {`${window.location.origin}/invitations/accept?token=${encodeURIComponent(token)}`}
          </code>
          <p className="mt-2 text-sm text-slate-400">
            Raw token (if needed separately):
          </p>
          <code className="mt-1 block break-all text-sm">{token}</code>
        </div>
      )}
    </section>
  );
}
