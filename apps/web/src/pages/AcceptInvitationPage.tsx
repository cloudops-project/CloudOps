import { useState } from "react";
import { useForm } from "react-hook-form";
import { useNavigate, useSearchParams } from "react-router";
import { api } from "../api/client";
import { useAuth } from "../auth/AuthProvider";
import { AuthCard, Field } from "../components/AuthCard";

export function AcceptInvitationPage() {
  const { reload } = useAuth();
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const [error, setError] = useState("");
  const {
    register,
    handleSubmit,
    formState: { isSubmitting },
  } = useForm<{ token: string }>({
    defaultValues: { token: params.get("token") || "" },
  });
  return (
    <AuthCard
      title="Accept invitation"
      subtitle="Join an existing CloudOps organization"
    >
      <form
        className="grid gap-4"
        onSubmit={handleSubmit(async (value) => {
          try {
            await api("/api/v1/invitations/accept", {
              method: "POST",
              body: JSON.stringify(value),
            });
            await reload();
            navigate("/dashboard");
          } catch (e) {
            setError(e instanceof Error ? e.message : "Invitation failed.");
          }
        })}
      >
        <Field label="Invitation token" required {...register("token")} />
        {error && (
          <p role="alert" className="text-red-400">
            {error}
          </p>
        )}
        <button className="button" disabled={isSubmitting}>
          Accept invitation
        </button>
      </form>
    </AuthCard>
  );
}
