import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Play, Search, ShieldAlert } from "lucide-react";
import type { ReactNode } from "react";
import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api/client";
import { useAuth } from "../auth/AuthProvider";
import {
  EvaluationStatusBadge,
  FindingStatusBadge,
  SafeEvidence,
  SeverityBadge,
} from "../components/FindingComponents";
import type {
  AWSAccount,
  EvaluationJob,
  Finding,
  FindingSeverity,
  FindingStatus,
  FindingSummary,
  Page,
  SecurityRule,
} from "../types";

function useOrganization() {
  return useAuth().me?.organizations[0];
}

const severities: FindingSeverity[] = [
  "critical",
  "high",
  "medium",
  "low",
  "informational",
];
const statuses: FindingStatus[] = ["open", "resolved", "suppressed"];

export function FindingsDashboardPage() {
  const organization = useOrganization();
  const summary = useQuery({
    queryKey: ["finding-summary", organization?.id],
    enabled: Boolean(organization),
    queryFn: () =>
      api<FindingSummary>(
        `/api/v1/findings/summary?organization_id=${organization!.id}`,
      ),
  });
  if (!organization) return <p>No organization selected.</p>;
  return (
    <section>
      <h1 className="text-3xl font-bold">Security findings</h1>
      <p className="text-slate-400">
        Deterministic results from persisted AWS inventory.
      </p>
      {summary.isLoading && <p aria-live="polite">Loading summary…</p>}
      {summary.isError && (
        <p role="alert" className="text-red-300">
          Unable to load the findings summary.
        </p>
      )}
      <div className="mt-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-5">
        {severities.map((severity) => (
          <article className="card" key={severity}>
            <SeverityBadge severity={severity} />
            <p className="mt-4 text-3xl font-extrabold">
              {summary.data?.items
                .filter(
                  (item) =>
                    item.severity === severity && item.status === "open",
                )
                .reduce((total, item) => total + item.count, 0) ?? 0}
            </p>
            <p className="text-sm text-slate-400">Open findings</p>
          </article>
        ))}
      </div>
      <div className="mt-6 flex flex-wrap gap-3">
        <Link className="button" to="/findings">
          <ShieldAlert size={18} />
          View findings
        </Link>
        <Link className="button-secondary" to="/rules">
          Rule catalog
        </Link>
        <Link className="button-secondary" to="/evaluations">
          Evaluations
        </Link>
      </div>
    </section>
  );
}

export function FindingsPage() {
  const organization = useOrganization();
  const [page, setPage] = useState(1);
  const [filters, setFilters] = useState({
    severity: "",
    status: "",
    aws_account_id: "",
    search: "",
  });
  const accounts = useQuery({
    queryKey: ["aws-accounts", organization?.id],
    enabled: Boolean(organization),
    queryFn: () =>
      api<AWSAccount[]>(
        `/api/v1/aws/accounts?organization_id=${organization!.id}`,
      ),
  });
  const queryString = useMemo(() => {
    const params = new URLSearchParams({
      organization_id: organization?.id ?? "",
      page: String(page),
      page_size: "25",
    });
    Object.entries(filters).forEach(([key, value]) => {
      if (value) params.set(key, value);
    });
    return params.toString();
  }, [filters, organization?.id, page]);
  const query = useQuery({
    queryKey: ["findings", queryString],
    enabled: Boolean(organization),
    queryFn: () => api<Page<Finding>>(`/api/v1/findings?${queryString}`),
  });
  const update = (key: string, value: string) => {
    setPage(1);
    setFilters((current) => ({ ...current, [key]: value }));
  };
  if (!organization) return <p>No organization selected.</p>;
  return (
    <section>
      <h1 className="text-3xl font-bold">Findings</h1>
      <div className="card my-5 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        <label>
          <span className="label">Search</span>
          <span className="relative block">
            <Search
              className="absolute left-3 top-3 text-slate-500"
              size={18}
            />
            <input
              aria-label="Search findings"
              className="input pl-10"
              value={filters.search}
              onChange={(event) => update("search", event.target.value)}
            />
          </span>
        </label>
        <Filter
          label="AWS account"
          value={filters.aws_account_id}
          onChange={(value) => update("aws_account_id", value)}
        >
          {accounts.data?.map((account) => (
            <option key={account.id} value={account.id}>
              {account.name}
            </option>
          ))}
        </Filter>
        <Filter
          label="Severity"
          value={filters.severity}
          onChange={(value) => update("severity", value)}
        >
          {severities.map((severity) => (
            <option key={severity} value={severity}>
              {severity}
            </option>
          ))}
        </Filter>
        <Filter
          label="Status"
          value={filters.status}
          onChange={(value) => update("status", value)}
        >
          {statuses.map((status) => (
            <option key={status} value={status}>
              {status}
            </option>
          ))}
        </Filter>
      </div>
      {query.isLoading && <p aria-live="polite">Loading findings…</p>}
      {query.isError && (
        <p role="alert" className="text-red-300">
          Unable to load findings.
        </p>
      )}
      {query.data?.total === 0 && (
        <div className="card">No findings match these filters.</div>
      )}
      <div className="grid gap-4">
        {query.data?.items.map((finding) => (
          <article className="card" key={finding.id}>
            <div className="flex flex-wrap items-center justify-between gap-3">
              <Link
                className="font-semibold text-blue-300"
                to={`/findings/${finding.id}`}
              >
                {finding.rule_key}
              </Link>
              <span className="flex gap-2">
                <SeverityBadge severity={finding.severity} />
                <FindingStatusBadge status={finding.status} />
              </span>
            </div>
          </article>
        ))}
      </div>
      <Pagination
        page={page}
        total={query.data?.total ?? 0}
        pageSize={query.data?.page_size ?? 25}
        onPage={setPage}
      />
    </section>
  );
}

export function FindingDetailsPage() {
  const organization = useOrganization();
  const { findingId } = useParams();
  const client = useQueryClient();
  const [suppressOpen, setSuppressOpen] = useState(false);
  const [reason, setReason] = useState("");
  const dialogRef = useRef<HTMLButtonElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const query = useQuery({
    queryKey: ["finding", findingId, organization?.id],
    enabled: Boolean(findingId && organization),
    queryFn: () =>
      api<Finding>(
        `/api/v1/findings/${findingId}?organization_id=${organization!.id}`,
      ),
  });
  const role = organization?.current_user_role;
  const canSuppress = Boolean(
    role && ["owner", "admin", "security_analyst"].includes(role),
  );
  const suppress = useMutation({
    mutationFn: () =>
      api<Finding>(
        `/api/v1/findings/${findingId}/suppress?organization_id=${organization!.id}`,
        { method: "POST", body: JSON.stringify({ reason }) },
      ),
    onSuccess: (finding) => {
      client.setQueryData(["finding", findingId, organization?.id], finding);
      setSuppressOpen(false);
      setReason("");
      queueMicrotask(() => triggerRef.current?.focus());
    },
  });
  const unsuppress = useMutation({
    mutationFn: () =>
      api<Finding>(
        `/api/v1/findings/${findingId}/unsuppress?organization_id=${organization!.id}`,
        { method: "POST" },
      ),
    onSuccess: (finding) =>
      client.setQueryData(["finding", findingId, organization?.id], finding),
  });
  useEffect(() => {
    if (suppressOpen) dialogRef.current?.focus();
  }, [suppressOpen]);
  if (query.isLoading) return <p>Loading finding…</p>;
  if (query.isError || !query.data)
    return (
      <p role="alert" className="text-red-300">
        Unable to load finding.
      </p>
    );
  const finding = query.data;
  return (
    <section className="grid gap-5">
      <Link
        className="inline-flex items-center gap-2 text-blue-300"
        to="/findings"
      >
        <ArrowLeft size={18} />
        Findings
      </Link>
      <article className="card">
        <div className="flex flex-wrap justify-between gap-3">
          <div>
            <h1 className="text-2xl font-bold">{finding.rule_key}</h1>
            <p className="text-slate-400">{finding.category}</p>
          </div>
          <span className="flex gap-2">
            <SeverityBadge severity={finding.severity} />
            <FindingStatusBadge status={finding.status} />
          </span>
        </div>
        {canSuppress && (
          <div className="mt-5">
            {finding.status === "suppressed" ? (
              <button
                className="button-secondary"
                onClick={() => unsuppress.mutate()}
              >
                Unsuppress finding
              </button>
            ) : (
              <button
                ref={triggerRef}
                className="button-secondary"
                onClick={() => setSuppressOpen(true)}
              >
                Suppress finding
              </button>
            )}
          </div>
        )}
      </article>
      <article className="card">
        <h2 className="mb-3 text-xl font-bold">Evidence</h2>
        <SafeEvidence value={finding.evidence} />
      </article>
      {suppressOpen && (
        <div className="fixed inset-0 z-50 grid place-items-center bg-slate-950/75 p-4">
          <div
            aria-labelledby="suppress-title"
            aria-modal="true"
            className="card w-full max-w-lg"
            role="dialog"
            onKeyDown={(event) => {
              if (event.key === "Escape" && !suppress.isPending) {
                setSuppressOpen(false);
                queueMicrotask(() => triggerRef.current?.focus());
              }
            }}
          >
            <h2 id="suppress-title" className="text-xl font-bold">
              Suppress finding
            </h2>
            <label className="mt-4 block">
              <span className="label">Suppression reason</span>
              <textarea
                className="input min-h-28"
                value={reason}
                onChange={(event) => setReason(event.target.value)}
              />
            </label>
            <div className="mt-5 flex justify-end gap-3">
              <button
                className="button-secondary"
                onClick={() => setSuppressOpen(false)}
              >
                Cancel
              </button>
              <button
                ref={dialogRef}
                className="button"
                disabled={reason.trim().length < 3 || suppress.isPending}
                onClick={() => suppress.mutate()}
              >
                {suppress.isPending ? "Suppressing…" : "Confirm suppression"}
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}

export function RuleCatalogPage() {
  const organization = useOrganization();
  const query = useQuery({
    queryKey: ["rules", organization?.id],
    enabled: Boolean(organization),
    queryFn: () =>
      api<SecurityRule[]>(`/api/v1/rules?organization_id=${organization!.id}`),
  });
  return (
    <section>
      <h1 className="text-3xl font-bold">Rule catalog</h1>
      {query.isLoading && <p>Loading rules…</p>}
      {query.isError && <p role="alert">Unable to load rules.</p>}
      <div className="mt-5 grid gap-4 md:grid-cols-2">
        {query.data?.map((rule) => (
          <article className="card" key={rule.key}>
            <div className="flex justify-between gap-3">
              <h2 className="font-bold">{rule.name}</h2>
              <SeverityBadge severity={rule.severity} />
            </div>
            <p className="mt-2 text-sm text-slate-300">{rule.description}</p>
            <p className="mt-3 font-mono text-xs text-blue-300">{rule.key}</p>
            <p className="mt-3 text-sm">
              <strong>Remediation:</strong> {rule.remediation}
            </p>
          </article>
        ))}
      </div>
    </section>
  );
}

export function EvaluationJobsPage() {
  const organization = useOrganization();
  const client = useQueryClient();
  const [selected, setSelected] = useState("");
  const [confirmOpen, setConfirmOpen] = useState(false);
  const confirmRef = useRef<HTMLButtonElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const accounts = useQuery({
    queryKey: ["aws-accounts", organization?.id],
    enabled: Boolean(organization),
    queryFn: () =>
      api<AWSAccount[]>(
        `/api/v1/aws/accounts?organization_id=${organization!.id}`,
      ),
  });
  const jobs = useQuery({
    queryKey: ["evaluations", organization?.id],
    enabled: Boolean(organization),
    queryFn: () =>
      api<Page<EvaluationJob>>(
        `/api/v1/evaluations?organization_id=${organization!.id}`,
      ),
  });
  const canRun = Boolean(
    organization &&
    ["owner", "admin", "security_analyst", "cloud_engineer"].includes(
      organization.current_user_role,
    ),
  );
  const start = useMutation({
    mutationFn: () =>
      api<EvaluationJob>(`/api/v1/aws/accounts/${selected}/evaluate`, {
        method: "POST",
        body: "{}",
      }),
    onSuccess: () => {
      setConfirmOpen(false);
      setSelected("");
      void client.invalidateQueries({ queryKey: ["evaluations"] });
      queueMicrotask(() => triggerRef.current?.focus());
    },
  });
  useEffect(() => {
    if (confirmOpen) confirmRef.current?.focus();
  }, [confirmOpen]);
  const selectedAccount = accounts.data?.find(
    (account) => account.id === selected,
  );
  return (
    <section>
      <h1 className="text-3xl font-bold">Evaluation jobs</h1>
      {canRun && (
        <div className="card my-5 flex flex-wrap items-end gap-3">
          <Filter label="AWS account" value={selected} onChange={setSelected}>
            {accounts.data
              ?.filter((account) => account.connection_status === "connected")
              .map((account) => (
                <option key={account.id} value={account.id}>
                  {account.name}
                </option>
              ))}
          </Filter>
          <button
            ref={triggerRef}
            className="button"
            disabled={!selected}
            onClick={() => setConfirmOpen(true)}
          >
            <Play size={18} />
            Run evaluation
          </button>
        </div>
      )}
      {jobs.isLoading && <p>Loading evaluations…</p>}
      {jobs.data?.total === 0 && (
        <div className="card">No evaluations yet.</div>
      )}
      <div className="grid gap-4">
        {jobs.data?.items.map((job) => (
          <article className="card" key={job.id}>
            <div className="flex justify-between gap-3">
              <strong>Evaluation #{job.sequence}</strong>
              <EvaluationStatusBadge status={job.status} />
            </div>
            <div className="mt-4 grid grid-cols-2 gap-3 text-sm md:grid-cols-4">
              <span>Rules: {job.rules_evaluated}</span>
              <span>Failed: {job.failed_count}</span>
              <span>Errors: {job.error_count}</span>
              <span>Created: {job.findings_created}</span>
            </div>
            {job.error_summary && (
              <p role="alert" className="mt-3 text-red-300">
                Evaluation completed with sanitized rule errors.
              </p>
            )}
          </article>
        ))}
      </div>
      {confirmOpen && selectedAccount && (
        <div className="fixed inset-0 z-50 grid place-items-center bg-slate-950/75 p-4">
          <div
            aria-labelledby="evaluation-confirm-title"
            aria-modal="true"
            className="card max-w-lg"
            role="dialog"
            onKeyDown={(event) => {
              if (event.key === "Escape" && !start.isPending)
                setConfirmOpen(false);
            }}
          >
            <h2 id="evaluation-confirm-title" className="text-xl font-bold">
              Confirm security evaluation
            </h2>
            <p className="mt-3 text-slate-300">
              CloudOps will deterministically evaluate persisted inventory for{" "}
              <strong>{selectedAccount.name}</strong>. No live AWS calls or
              resource changes occur.
            </p>
            <div className="mt-5 flex justify-end gap-3">
              <button
                className="button-secondary"
                disabled={start.isPending}
                onClick={() => setConfirmOpen(false)}
              >
                Cancel
              </button>
              <button
                ref={confirmRef}
                className="button"
                disabled={start.isPending}
                onClick={() => {
                  if (!start.isPending) start.mutate();
                }}
              >
                {start.isPending ? "Evaluating…" : "Confirm evaluation"}
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}

function Filter({
  label,
  value,
  onChange,
  children,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  children: ReactNode;
}) {
  return (
    <label>
      <span className="label">{label}</span>
      <select
        className="input"
        value={value}
        onChange={(event) => onChange(event.target.value)}
      >
        <option value="">All</option>
        {children}
      </select>
    </label>
  );
}

function Pagination({
  page,
  total,
  pageSize,
  onPage,
}: {
  page: number;
  total: number;
  pageSize: number;
  onPage: (value: number) => void;
}) {
  return (
    <div className="mt-5 flex items-center justify-between">
      <button
        className="button-secondary"
        disabled={page === 1}
        onClick={() => onPage(page - 1)}
      >
        Previous
      </button>
      <span>Page {page}</span>
      <button
        className="button-secondary"
        disabled={page * pageSize >= total}
        onClick={() => onPage(page + 1)}
      >
        Next
      </button>
    </div>
  );
}
