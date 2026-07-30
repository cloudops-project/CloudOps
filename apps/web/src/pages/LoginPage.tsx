import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { Link, useLocation, useNavigate } from "react-router";
import { z } from "zod";
import { useAuth } from "../auth/AuthProvider";
import { AuthCard, Field } from "../components/AuthCard";

const schema = z.object({
  email: z.email("Enter a valid email."),
  password: z.string().min(1, "Password is required."),
});
type Values = z.infer<typeof schema>;
export function LoginPage() {
  const { signIn } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<Values>({ resolver: zodResolver(schema) });
  return (
    <AuthCard
      title="Welcome back"
      subtitle="Sign in to your CloudOps workspace"
    >
      <form
        className="grid gap-4"
        onSubmit={handleSubmit(async (values) => {
          try {
            await signIn(values.email, values.password);
            navigate(
              (location.state as { from?: string } | null)?.from ||
                "/dashboard",
              { replace: true },
            );
          } catch (error) {
            setError("root", {
              message:
                error instanceof Error ? error.message : "Sign in failed.",
            });
          }
        })}
      >
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
          autoComplete="current-password"
          error={errors.password?.message}
          {...register("password")}
        />
        {errors.root && (
          <p role="alert" className="text-sm text-red-400">
            {errors.root.message}
          </p>
        )}
        <button className="button w-full" disabled={isSubmitting}>
          {isSubmitting ? "Signing in…" : "Sign in"}
        </button>
        <p className="text-center text-sm text-slate-400">
          New to CloudOps?{" "}
          <Link className="text-blue-400 hover:underline" to="/register">
            Create account
          </Link>
        </p>
      </form>
    </AuthCard>
  );
}
