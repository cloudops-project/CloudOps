import type { ReactNode } from "react";
import { ShieldCheck } from "lucide-react";

export function AuthCard({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle: string;
  children: ReactNode;
}) {
  return (
    <main className="grid min-h-screen place-items-center bg-canvas p-5">
      <section className="card w-full max-w-md" aria-labelledby="auth-title">
        <div className="mb-6 flex items-center gap-3">
          <span className="rounded-button bg-blue-600/20 p-3 text-blue-400">
            <ShieldCheck />
          </span>
          <div>
            <h1 id="auth-title" className="text-2xl font-bold">
              {title}
            </h1>
            <p className="text-sm text-slate-400">{subtitle}</p>
          </div>
        </div>
        {children}
      </section>
    </main>
  );
}

export function Field({
  label,
  error,
  ...props
}: React.InputHTMLAttributes<HTMLInputElement> & {
  label: string;
  error?: string;
}) {
  return (
    <label className="block">
      <span className="label">{label}</span>
      <input className="input" aria-invalid={Boolean(error)} {...props} />
      {error && (
        <span role="alert" className="mt-1 block text-sm text-red-400">
          {error}
        </span>
      )}
    </label>
  );
}
