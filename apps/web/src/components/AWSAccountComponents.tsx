import { CheckCircle2, Cloud, TriangleAlert } from "lucide-react";
import type { ReactNode } from "react";
import { Link } from "react-router";
import type { AWSAccount, AWSAccountStatus } from "../types";

const statusClasses: Record<AWSAccountStatus, string> = {
  connected: "bg-green-500/15 text-green-300",
  pending: "bg-amber-500/15 text-amber-300",
  failed: "bg-red-500/15 text-red-300",
  disconnected: "bg-slate-500/20 text-slate-300",
};

export function ConnectionStatusBadge({
  status,
}: {
  status: AWSAccountStatus;
}) {
  return (
    <span
      className={`rounded-full px-3 py-1 text-xs font-bold uppercase ${statusClasses[status]}`}
    >
      {status}
    </span>
  );
}

export function AccountCard({ account }: { account: AWSAccount }) {
  return (
    <article className="card transition-transform duration-150 hover:-translate-y-0.5">
      <div className="flex items-start justify-between gap-4">
        <Cloud className="text-blue-400" aria-hidden="true" />
        <ConnectionStatusBadge status={account.connection_status} />
      </div>
      <h2 className="mt-4 text-xl font-bold">{account.name}</h2>
      <p className="mt-1 font-mono text-sm text-slate-400">
        {account.account_id}
      </p>
      <Link
        className="button-secondary mt-5 w-full"
        to={`/aws/accounts/${account.id}`}
      >
        View account
      </Link>
    </article>
  );
}

export function PolicyViewer({
  title,
  value,
}: {
  title: string;
  value: unknown;
}) {
  return (
    <section className="card">
      <h2 className="text-xl font-bold">{title}</h2>
      <pre className="mt-4 max-h-96 overflow-auto rounded-button bg-slate-950 p-4 text-xs text-slate-200">
        {JSON.stringify(value, null, 2)}
      </pre>
    </section>
  );
}

export function IAMSetupInstructions({ steps }: { steps: string[] }) {
  return (
    <section className="card">
      <h2 className="text-xl font-bold">IAM setup instructions</h2>
      <ol className="mt-4 grid list-decimal gap-3 pl-5 text-slate-300">
        {steps.map((step) => (
          <li key={step}>{step}</li>
        ))}
      </ol>
    </section>
  );
}

export function ValidationResult({
  ok,
  children,
}: {
  ok: boolean;
  children: ReactNode;
}) {
  return (
    <div
      role={ok ? "status" : "alert"}
      className={`card flex gap-3 ${ok ? "text-green-300" : "text-red-300"}`}
    >
      {ok ? <CheckCircle2 /> : <TriangleAlert />}
      <div>{children}</div>
    </div>
  );
}
