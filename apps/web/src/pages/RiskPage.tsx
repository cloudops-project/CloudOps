import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { Link } from "react-router";
import { api } from "../api/client";
import { useAuth } from "../auth/AuthProvider";
import { AIWorkflow } from "../components/AIWorkflow";
import type {
  FindingRisk,
  Page,
  RiskAssessment,
  RiskPriority,
  RiskSummary,
} from "../types";

const assessmentRoles = [
  "owner",
  "admin",
  "security_analyst",
  "cloud_engineer",
];
const priorities: Array<RiskPriority | ""> = [
  "",
  "critical",
  "high",
  "medium",
  "low",
];

function Score({ value, priority }: { value: number; priority: string }) {
  return (
    <span
      className="inline-flex items-center gap-2 rounded-full border border-slate-600 px-3 py-1"
      aria-label={`Risk score ${value}, priority ${priority}`}
    >
      <strong>{value}</strong>
      <span className="uppercase">{priority}</span>
    </span>
  );
}

function AssessmentDialog({ organizationId }: { organizationId: string }) {
  const [open, setOpen] = useState(false);
  const cancelRef = useRef<HTMLButtonElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const queryClient = useQueryClient();
  const mutation = useMutation({
    mutationFn: () =>
      api<RiskAssessment>("/api/v1/risk/assess", {
        method: "POST",
        body: JSON.stringify({ organization_id: organizationId }),
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["risk"] });
      setOpen(false);
      triggerRef.current?.focus();
    },
  });
  useEffect(() => {
    if (open) cancelRef.current?.focus();
  }, [open]);
  return (
    <>
      <button
        ref={triggerRef}
        className="button-primary"
        onClick={() => setOpen(true)}
      >
        Recalculate risk
      </button>
      {open && (
        <div
          className="fixed inset-0 z-50 grid place-items-center bg-slate-950/80 p-4"
          role="dialog"
          aria-modal="true"
          aria-labelledby="risk-dialog-title"
          onKeyDown={(event) => {
            if (event.key === "Escape" && !mutation.isPending) {
              setOpen(false);
              triggerRef.current?.focus();
            }
          }}
        >
          <div className="card max-w-lg">
            <h2 id="risk-dialog-title" className="text-xl font-bold">
              Recalculate deterministic risk?
            </h2>
            <p className="mt-3 text-slate-300">
              CloudOps will score current persisted findings. No live AWS calls
              or resource changes are made.
            </p>
            {mutation.isError && (
              <p role="alert" className="mt-3 text-red-300">
                Risk assessment failed safely.
              </p>
            )}
            <div className="mt-5 flex gap-3">
              <button
                ref={cancelRef}
                className="button-secondary"
                disabled={mutation.isPending}
                onClick={() => {
                  setOpen(false);
                  triggerRef.current?.focus();
                }}
              >
                Cancel
              </button>
              <button
                className="button-primary"
                disabled={mutation.isPending}
                onClick={() => mutation.mutate()}
              >
                {mutation.isPending ? "Calculating…" : "Confirm"}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

function FindingRow({ item }: { item: FindingRisk }) {
  return (
    <tr>
      <td className="px-3 py-3">
        <Link
          className="text-blue-300 underline"
          to={`/findings/${item.finding_id}`}
        >
          {item.rule_key}
        </Link>
      </td>
      <td className="px-3 py-3">{item.asset_name ?? "Account-level"}</td>
      <td className="px-3 py-3">
        <Score value={item.risk_score} priority={item.priority} />
      </td>
      <td className="px-3 py-3">{item.severity}</td>
      <td className="px-3 py-3">{item.finding_status}</td>
    </tr>
  );
}

export function RiskPage() {
  const organization = useAuth().me?.organizations[0];
  const [priority, setPriority] = useState<RiskPriority | "">("");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const summary = useQuery({
    queryKey: ["risk", "summary", organization?.id],
    enabled: Boolean(organization),
    queryFn: () =>
      api<RiskSummary>(
        `/api/v1/risk/summary?organization_id=${organization!.id}`,
      ),
  });
  const findings = useQuery({
    queryKey: ["risk", "findings", organization?.id, priority, search, page],
    enabled: Boolean(organization),
    queryFn: () => {
      const params = new URLSearchParams({
        organization_id: organization!.id,
        page: String(page),
        page_size: "10",
      });
      if (priority) params.set("priority", priority);
      if (search.trim()) params.set("search", search.trim());
      return api<Page<FindingRisk>>(`/api/v1/risk/findings?${params}`);
    },
  });
  if (!organization) return <p>No organization selected.</p>;
  const mayAssess = assessmentRoles.includes(organization.role);
  return (
    <section aria-labelledby="risk-title">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 id="risk-title" className="text-3xl font-bold">
            Risk
          </h1>
          <p className="mt-2 text-slate-400">
            Explainable deterministic scores derived from persisted Stage 4
            findings. Unknown context is explicit, never silently zero.
          </p>
        </div>
        {mayAssess && <AssessmentDialog organizationId={organization.id} />}
      </div>
      {summary.isLoading && <p aria-live="polite">Loading risk summary…</p>}
      {summary.isError && <p role="alert">Unable to load risk summary.</p>}
      <div className="mt-5 grid gap-3 sm:grid-cols-3">
        <article className="card">
          <p className="text-sm text-slate-400">Organization risk</p>
          <p className="mt-2 text-3xl font-extrabold">
            {summary.data?.current?.risk_score ?? "—"}
          </p>
          <p>{summary.data?.current?.priority ?? "Not assessed"}</p>
        </article>
        <article className="card">
          <p className="text-sm text-slate-400">Critical findings</p>
          <p className="mt-2 text-3xl font-extrabold">
            {summary.data?.assessment?.critical_count ?? 0}
          </p>
        </article>
        <article className="card">
          <p className="text-sm text-slate-400">Accounts scored</p>
          <p className="mt-2 text-3xl font-extrabold">
            {summary.data?.assessment?.accounts_scored ?? 0}
          </p>
        </article>
      </div>
      {summary.data?.assessment && (
        <div className="mt-5">
          <AIWorkflow
            organization={organization}
            sourceType="risk_assessment"
            sourceId={summary.data.assessment.id}
            tasks={["executive_summary", "email_summary"]}
          />
        </div>
      )}
      <div className="mt-8 flex flex-wrap gap-3">
        <label>
          Priority
          <select
            className="input mt-1 block"
            value={priority}
            onChange={(event) => {
              setPriority(event.target.value as RiskPriority | "");
              setPage(1);
            }}
          >
            {priorities.map((item) => (
              <option key={item || "all"} value={item}>
                {item || "All priorities"}
              </option>
            ))}
          </select>
        </label>
        <label>
          Search
          <input
            className="input mt-1 block"
            value={search}
            onChange={(event) => {
              setSearch(event.target.value);
              setPage(1);
            }}
          />
        </label>
      </div>
      {findings.isLoading && <p aria-live="polite">Loading risk findings…</p>}
      {findings.isError && <p role="alert">Unable to load risk findings.</p>}
      {findings.data?.items.length === 0 && (
        <p className="mt-5">No risk findings.</p>
      )}
      {Boolean(findings.data?.items.length) && (
        <div className="mt-5 overflow-x-auto">
          <table className="w-full text-left">
            <thead>
              <tr>
                <th className="px-3 py-2">Rule</th>
                <th className="px-3 py-2">Asset</th>
                <th className="px-3 py-2">Score and priority</th>
                <th className="px-3 py-2">Severity</th>
                <th className="px-3 py-2">Finding status</th>
              </tr>
            </thead>
            <tbody>
              {findings.data?.items.map((item) => (
                <FindingRow key={item.id} item={item} />
              ))}
            </tbody>
          </table>
        </div>
      )}
      <div className="mt-5 flex gap-3">
        <button
          className="button-secondary"
          disabled={page === 1}
          onClick={() => setPage((value) => value - 1)}
        >
          Previous
        </button>
        <button
          className="button-secondary"
          disabled={page * 10 >= (findings.data?.total ?? 0)}
          onClick={() => setPage((value) => value + 1)}
        >
          Next
        </button>
      </div>
    </section>
  );
}
