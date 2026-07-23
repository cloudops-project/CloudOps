import { useState } from "react";
import { useForm } from "react-hook-form";
import { api } from "../api/client";
import { useAuth } from "../auth/AuthProvider";
import { Field } from "../components/AuthCard";

export function ProfilePage() {
  const { me, signOut } = useAuth();
  const [message, setMessage] = useState("");
  const { register, handleSubmit } = useForm<{
    current_password: string;
    new_password: string;
  }>();
  return (
    <div className="grid gap-6">
      <section className="card">
        <h1 className="text-3xl font-bold">User profile</h1>
        <dl className="mt-5 grid gap-2">
          <div>
            <dt className="text-sm text-slate-400">Name</dt>
            <dd>{me?.user.full_name}</dd>
          </div>
          <div>
            <dt className="text-sm text-slate-400">Email</dt>
            <dd>{me?.user.email}</dd>
          </div>
        </dl>
      </section>
      <section className="card max-w-xl">
        <h2 className="text-xl font-bold">Change password</h2>
        <form
          className="mt-4 grid gap-4"
          onSubmit={handleSubmit(async (values) => {
            try {
              await api("/api/v1/auth/change-password", {
                method: "POST",
                body: JSON.stringify(values),
              });
              setMessage("Password changed. Please sign in again.");
              setTimeout(() => void signOut(), 800);
            } catch (e) {
              setMessage(
                e instanceof Error ? e.message : "Password change failed.",
              );
            }
          })}
        >
          <Field
            label="Current password"
            type="password"
            {...register("current_password")}
          />
          <Field
            label="New password"
            type="password"
            {...register("new_password")}
          />
          <button className="button">Change password</button>
          {message && <p role="status">{message}</p>}
        </form>
      </section>
    </div>
  );
}
