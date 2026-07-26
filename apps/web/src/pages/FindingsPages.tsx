import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Play, Search, ShieldAlert } from "lucide-react";
import type { KeyboardEvent as ReactKeyboardEvent, ReactNode } from "react";
import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useParams } from "react-router";
import { api, ApiError } from "../api/client";
import { useAuth } from "../auth/AuthProvider";
import { AIWorkflow } from "../components/AIWorkflow";
import {
  EvaluationStatusBadge,
  FindingStatusBadge,
  SafeEvidence,
  SeverityBadge,
} from "../components/FindingComponents";
import type {
  AssetType,
  AWSAccount,
  EvaluationJob,
  Finding,
  FindingSeverity,
  FindingStatus,
  FindingSummary,
  Page,
  RemediationRequest,
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
const services = [
  "ec2",
  "s3",
  "iam",
  "rds",
  "cloudwatch",
  "cloudwatch_logs",
  "cloudtrail",
];
const assetTypes: AssetType[] = [
  "ec2_instance",
  "ec2_security_group",
  "ebs_volume",
  "s3_bucket",
  "iam_user",
  "iam_role",
  "iam_group",
  "iam_policy",
  "rds_instance",
  "cloudwatch_alarm",
  "cloudwatch_log_group",
  "cloudtrail_trail",
];

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
      <div className="mt-6 grid gap-4 sm:grid-cols-3">
        {statuses.map((status) => (
          <article className="card" key={status}>
            <FindingStatusBadge status={status} />
            <p className="mt-4 text-3xl font-extrabold">
              {summary.data?.items
                .filter((item) => item.status === status)
                .reduce((total, item) => total + item.count, 0) ?? 0}
            </p>
            <p className="text-sm text-slate-400">All severities</p>
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
    asset_id: "",
    service: "",
    asset_type: "",
    region: "",
    rule_key: "",
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
          label="Service"
          value={filters.service}
          onChange={(value) => update("service", value)}
        >
          {services.map((service) => (
            <option key={service} value={service}>
              {service.replaceAll("_", " ")}
            </option>
          ))}
        </Filter>
        <Filter
          label="Asset type"
          value={filters.asset_type}
          onChange={(value) => update("asset_type", value)}
        >
          {assetTypes.map((type) => (
            <option key={type} value={type}>
              {type.replaceAll("_", " ")}
            </option>
          ))}
        </Filter>
        <label>
          <span className="label">Region</span>
          <input
            className="input"
            value={filters.region}
            onChange={(event) => update("region", event.target.value)}
          />
        </label>
        <label>
          <span className="label">Rule</span>
          <input
            className="input"
            value={filters.rule_key}
            onChange={(event) => update("rule_key", event.target.value)}
          />
        </label>
        <label>
          <span className="label">Asset ID</span>
          <input
            className="input"
            value={filters.asset_id}
            onChange={(event) => update("asset_id", event.target.value)}
          />
        </label>
        <button
          className="button-secondary self-end"
          onClick={() => {
            setFilters({
              severity: "",
              status: "",
              aws_account_id: "",
              asset_id: "",
              service: "",
              asset_type: "",
              region: "",
              rule_key: "",
              search: "",
            });
            setPage(1);
          }}
        >
          Clear filters
        </button>
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
            <dl className="mt-3 grid gap-2 text-sm text-slate-300 sm:grid-cols-3">
              <div>
                <dt className="text-slate-500">Service</dt>
                <dd>{finding.service}</dd>
              </div>
              <div>
                <dt className="text-slate-500">Region</dt>
                <dd>{finding.region ?? "Account-level"}</dd>
              </div>
              <div>
                <dt className="text-slate-500">Last seen</dt>
                <dd>{new Date(finding.last_seen_at).toLocaleString()}</dd>
              </div>
            </dl>
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
  const [suppressedUntil, setSuppressedUntil] = useState("");
  const dialogRef = useRef<HTMLButtonElement>(null);
  const dialogContainerRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const query = useQuery({
    queryKey: ["finding", findingId, organization?.id],
    enabled: Boolean(findingId && organization),
    queryFn: () =>
      api<Finding>(
        `/api/v1/findings/${findingId}?organization_id=${organization!.id}`,
      ),
  });
  const role = organization?.role;
  const canSuppress = Boolean(
    role && ["owner", "admin", "security_analyst"].includes(role),
  );
  const canProposeRemediation = Boolean(
    role &&
    ["owner", "admin", "security_analyst", "cloud_engineer"].includes(role),
  );
  const [remediationError, setRemediationError] = useState<string | null>(null);
  const proposeRemediation = useMutation({
    mutationFn: () =>
      api<RemediationRequest>(
        `/api/v1/findings/${findingId}/remediations?organization_id=${organization!.id}`,
        { method: "POST" },
      ),
    onSuccess: () => setRemediationError(null),
    onError: (err: unknown) =>
      setRemediationError(
        err instanceof ApiError
          ? err.message
          : "Unable to propose remediation.",
      ),
  });
  const suppress = useMutation({
    mutationFn: () =>
      api<Finding>(
        `/api/v1/findings/${findingId}/suppress?organization_id=${organization!.id}`,
        {
          method: "POST",
          body: JSON.stringify({
            reason,
            suppressed_until: suppressedUntil
              ? new Date(suppressedUntil).toISOString()
              : null,
          }),
        },
      ),
    onSuccess: (finding) => {
      client.setQueryData(["finding", findingId, organization?.id], finding);
      setSuppressOpen(false);
      setReason("");
      setSuppressedUntil("");
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
        {canProposeRemediation && finding.status === "open" && (
          <div className="mt-5">
            {proposeRemediation.isSuccess ? (
              <p className="text-slate-300">
                Remediation proposed.{" "}
                <Link className="text-blue-300" to="/remediations">
                  View remediation requests
                </Link>
                .
              </p>
            ) : (
              <button
                className="button"
                disabled={proposeRemediation.isPending}
                onClick={() => proposeRemediation.mutate()}
              >
                {proposeRemediation.isPending
                  ? "Proposing…"
                  : "Propose remediation"}
              </button>
            )}
            {remediationError && (
              <p role="alert" className="mt-2 text-sm text-red-300">
                {remediationError}
              </p>
            )}
          </div>
        )}
      </article>
      <article className="card">
        <h2 className="text-xl font-bold">Finding details</h2>
        <dl className="mt-4 grid gap-3 sm:grid-cols-2">
          <div>
            <dt className="label">Rule version</dt>
            <dd>{finding.rule_version}</dd>
          </div>
          <div>
            <dt className="label">Service</dt>
            <dd>{finding.service}</dd>
          </div>
          <div>
            <dt className="label">Asset type</dt>
            <dd>{finding.asset_type ?? "Account-level"}</dd>
          </div>
          <div>
            <dt className="label">Region</dt>
            <dd>{finding.region ?? "Not applicable"}</dd>
          </div>
          <div>
            <dt className="label">First seen</dt>
            <dd>{new Date(finding.first_seen_at).toLocaleString()}</dd>
          </div>
          <div>
            <dt className="label">Last seen</dt>
            <dd>{new Date(finding.last_seen_at).toLocaleString()}</dd>
          </div>
          <div>
            <dt className="label">Suppression</dt>
            <dd>{finding.suppression_reason ?? "Not suppressed"}</dd>
          </div>
        </dl>
        <h3 className="mt-5 font-bold">Remediation</h3>
        <p className="text-slate-300">{finding.remediation}</p>
        {(finding.references ?? []).length > 0 && (
          <>
            <h3 className="mt-5 font-bold">References</h3>
            <ul className="list-disc pl-6">
              {(finding.references ?? []).map((reference) => (
                <li key={reference}>{reference}</li>
              ))}
            </ul>
          </>
        )}
      </article>
      <article className="card">
        <h2 className="mb-3 text-xl font-bold">Evidence</h2>
        <SafeEvidence value={finding.evidence} />
      </article>
      {organization && (
        <AIWorkflow
          organization={organization}
          sourceType="finding"
          sourceId={finding.id}
          tasks={[
            "explain_finding",
            "explain_business_impact",
            "suggest_remediation",
            "jira_description",
            "email_summary",
          ]}
        />
      )}
      {suppressOpen && (
        <div className="fixed inset-0 z-50 grid place-items-center bg-slate-950/75 p-4">
          <div
            ref={dialogContainerRef}
            aria-labelledby="suppress-title"
            aria-modal="true"
            className="card w-full max-w-lg"
            role="dialog"
            onKeyDown={(event) => {
              trapDialogFocus(event, dialogContainerRef.current);
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
            <label className="mt-4 block">
              <span className="label">Expiry (optional)</span>
              <input
                className="input"
                type="datetime-local"
                value={suppressedUntil}
                onChange={(event) => setSuppressedUntil(event.target.value)}
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
  const confirmContainerRef = useRef<HTMLDivElement>(null);
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
      organization.role,
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
              <span>Updated: {job.findings_updated}</span>
              <span>Resolved: {job.findings_resolved}</span>
              <span>Reopened: {job.findings_reopened}</span>
              <span>Evaluation errors: {job.evaluation_errors}</span>
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
            ref={confirmContainerRef}
            aria-labelledby="evaluation-confirm-title"
            aria-modal="true"
            className="card max-w-lg"
            role="dialog"
            onKeyDown={(event) => {
              trapDialogFocus(event, confirmContainerRef.current);
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

function trapDialogFocus(
  event: ReactKeyboardEvent<HTMLDivElement>,
  container: HTMLDivElement | null,
) {
  if (event.key !== "Tab" || !container) return;
  const controls = Array.from(
    container.querySelectorAll<HTMLElement>(
      "button:not([disabled]), input:not([disabled]), textarea:not([disabled]), select:not([disabled]), a[href]",
    ),
  );
  if (controls.length === 0) return;
  const first = controls[0];
  const last = controls[controls.length - 1];
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault();
    last.focus();
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault();
    first.focus();
  }
}
