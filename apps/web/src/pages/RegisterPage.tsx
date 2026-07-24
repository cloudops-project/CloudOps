import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { Link, useNavigate } from "react-router";
import { z } from "zod";
import { ApiError, api } from "../api/client";
import { AuthCard, Field } from "../components/AuthCard";

const schema = z.object({
  full_name: z.string().min(2),
  email: z.email(),
  password: z
    .string()
    .min(12, "Use at least 12 characters.")
    .regex(/[A-Z]/, "Add an uppercase letter.")
    .regex(/[a-z]/, "Add a lowercase letter.")
    .regex(/[0-9]/, "Add a number.")
    .regex(/[^\w\s]/, "Add a symbol."),
  organization_name: z.string().optional(),
});
type Values = z.infer<typeof schema>;
export function RegisterPage() {
  const navigate = useNavigate();
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<Values>({ resolver: zodResolver(schema) });
  return (
    <AuthCard
      title="Create your account"
      subtitle="Start an organization or accept an invitation"
    >
      <form
        className="grid gap-4"
        onSubmit={handleSubmit(async (values) => {
          try {
            const payload = {
              ...values,
              organization_name: values.organization_name?.trim() || undefined,
            };
            await api(
              "/api/v1/auth/register",
              { method: "POST", body: JSON.stringify(payload) },
              false,
            );
            navigate("/login");
          } catch (error) {
            if (error instanceof ApiError && error.details.length > 0) {
              let fieldErrorApplied = false;
              for (const detail of error.details) {
                const field = detail.field.split(".").at(-1);
                if (
                  field === "full_name" ||
                  field === "email" ||
                  field === "password" ||
                  field === "organization_name"
                ) {
                  setError(field, { message: detail.message });
                  fieldErrorApplied = true;
                }
              }
              if (fieldErrorApplied) return;
            }
            setError("root", {
              message:
                error instanceof Error ? error.message : "Registration failed.",
            });
          }
        })}
      >
        <Field
          label="Full name"
          autoComplete="name"
          error={errors.full_name?.message}
          {...register("full_name")}
        />
        <Field
          label="Email"
          type="email"
          autoComplete="email"
          error={errors.email?.message}
          {...register("email")}
        />
        <Field
          label="Password"
          type="password"
          autoComplete="new-password"
          error={errors.password?.message}
          {...register("password")}
        />
        <Field
          label="Organization name (optional)"
          error={errors.organization_name?.message}
          {...register("organization_name")}
        />
        {errors.root && (
          <p role="alert" className="text-sm text-red-400">
            {errors.root.message}
          </p>
        )}
        <button className="button" disabled={isSubmitting}>
          {isSubmitting ? "Creating…" : "Create account"}
        </button>
        <Link className="text-center text-sm text-blue-400" to="/login">
          Back to sign in
        </Link>
      </form>
    </AuthCard>
  );
}
