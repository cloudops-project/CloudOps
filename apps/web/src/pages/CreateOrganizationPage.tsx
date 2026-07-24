import { useState } from "react";
import { useForm } from "react-hook-form";
import { useNavigate } from "react-router";
import { api } from "../api/client";
import { useAuth } from "../auth/AuthProvider";
import { Field } from "../components/AuthCard";

export function CreateOrganizationPage() {
  const { reload } = useAuth();
  const navigate = useNavigate();
  const [error, setError] = useState("");
  const {
    register,
    handleSubmit,
    formState: { isSubmitting },
  } = useForm<{ name: string; slug: string }>();
  return (
    <section className="card max-w-xl">
      <h1 className="text-3xl font-bold">Create organization</h1>
      <p className="mt-2 text-slate-400">You will become the first owner.</p>
      <form
        className="mt-6 grid gap-4"
        onSubmit={handleSubmit(async (values) => {
          try {
            await api("/api/v1/organizations", {
              method: "POST",
              body: JSON.stringify({
                name: values.name,
                slug: values.slug || undefined,
              }),
            });
            await reload();
            navigate("/dashboard");
          } catch (e) {
            setError(e instanceof Error ? e.message : "Creation failed.");
          }
        })}
      >
        <Field label="Name" required {...register("name")} />
        <Field
          label="Slug"
          pattern="[a-z0-9]+(?:-[a-z0-9]+)*"
          {...register("slug")}
        />
        {error && (
          <p role="alert" className="text-red-400">
            {error}
          </p>
        )}
        <button className="button" disabled={isSubmitting}>
          Create organization
        </button>
      </form>
    </section>
  );
}
