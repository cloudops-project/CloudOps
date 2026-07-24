import {
  useMutation,
  useQueries,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { Link, useParams } from "react-router";
import { ApiError, api } from "../api/client";
import { useAuth } from "../auth/AuthProvider";
import { AIWorkflow } from "../components/AIWorkflow";
import type {
  AWSAccount,
  ComplianceAssessment,
  ComplianceAssessmentControl,
  ComplianceControl,
  ComplianceControlFindings,
  ComplianceFramework,
  ComplianceSummary,
  Finding,
  Page,
  RuleControlMapping,
} from "../types";

const assessmentRoles = [
  "owner",
  "admin",
  "security_analyst",
  "cloud_engineer",
];
const controlStatuses = ["pass", "fail", "not_assessed", "error"];

function useOrganization() {
  return useAuth().me?.organizations[0];
}

function useFrameworks() {
  const organization = useOrganization();
  return useQuery({
    queryKey: ["compliance-frameworks", organization?.id],
    enabled: Boolean(organization),
    queryFn: () =>
      api<ComplianceFramework[]>(
        `/api/v1/compliance/frameworks?organization_id=${organization!.id}`,
      ),
  });
}

function useAccounts() {
  const organization = useOrganization();
  return useQuery({
    queryKey: ["aws-accounts", organization?.id],
    enabled: Boolean(organization),
    queryFn: () =>
      api<AWSAccount[]>(
        `/api/v1/aws/accounts?organization_id=${organization!.id}`,
      ),
  });
}

function StatusText({ value }: { value: string }) {
  return (
    <span className="inline-flex rounded-full border border-slate-600 px-3 py-1 text-xs font-semibold uppercase">
      Status: {value.replaceAll("_", " ")}
    </span>
  );
}

function LoadState({
  loading,
  error,
  label,
}: {
  loading: boolean;
  error: boolean;
  label: string;
}) {
  if (loading) return <p aria-live="polite">Loading {label}…</p>;
  if (error)
    return (
      <p className="text-red-300" role="alert">
        Unable to load {label}.
      </p>
    );
  return null;
}

function CounterGrid({ summary }: { summary?: ComplianceSummary }) {
  const counters = [
    ["PASS", summary?.controls_passed ?? 0],
    ["FAIL", summary?.controls_failed ?? 0],
    ["NOT ASSESSED", summary?.controls_not_assessed ?? 0],
    ["ERROR", summary?.controls_error ?? 0],
  ];
  return (
    <div className="mt-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
      {counters.map(([label, value]) => (
        <article className="card" key={label}>
          <p className="text-sm text-slate-400">{label}</p>
          <p className="mt-2 text-3xl font-extrabold">{value}</p>
        </article>
      ))}
    </div>
  );
}

export function CompliancePage() {
  const organization = useOrganization();
  const frameworks = useFrameworks();
  const accounts = useAccounts();
  const summary = useQuery({
    queryKey: ["compliance-summary", organization?.id],
    enabled: Boolean(organization),
    queryFn: () =>
      api<ComplianceSummary>(
        `/api/v1/compliance/summary?organization_id=${organization!.id}`,
      ),
  });
  const assessments = useQuery({
    queryKey: ["compliance-assessments", organization?.id, "latest"],
    enabled: Boolean(organization),
    queryFn: () =>
      api<Page<ComplianceAssessment>>(
        `/api/v1/compliance/assessments?organization_id=${organization!.id}&page_size=5`,
      ),
  });
  if (!organization) return <p>No organization selected.</p>;
  const mayAssess = assessmentRoles.includes(organization.role);
  return (
    <section aria-labelledby="compliance-title">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 id="compliance-title" className="text-3xl font-bold">
            Compliance
          </h1>
          <p className="mt-2 text-slate-400">
            CloudOps interprets persisted deterministic Stage 4 evidence.
            Missing evidence is NOT_ASSESSED, never PASS.
          </p>
        </div>
        {mayAssess && (
          <AssessmentDialog
            frameworks={frameworks.data ?? []}
            accounts={accounts.data ?? []}
          />
        )}
      </div>
      <LoadState
        loading={summary.isLoading}
        error={summary.isError}
        label="compliance summary"
      />
      <CounterGrid summary={summary.data} />
      <h2 className="mt-10 text-xl font-bold">Frameworks</h2>
      <LoadState
        loading={frameworks.isLoading}
        error={frameworks.isError}
        label="frameworks"
      />
      {frameworks.data?.length === 0 && (
        <p className="mt-3">No compliance frameworks are available.</p>
      )}
      <div className="mt-4 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {frameworks.data?.map((framework) => (
          <article className="card" key={framework.id}>
            <h3 className="font-bold">{framework.name}</h3>
            <p className="text-sm text-slate-400">
              Version {framework.version}
            </p>
            <p className="mt-3 text-sm">
              CloudOps summary: {framework.description}
            </p>
            <div className="mt-4 flex flex-wrap gap-3">
              <Link
                className="text-blue-300 underline"
                to={`/compliance/frameworks/${framework.key}`}
              >
                View framework
              </Link>
              <a
                className="text-blue-300 underline"
                href={framework.official_reference}
                rel="noreferrer"
                target="_blank"
              >
                Official reference
              </a>
            </div>
          </article>
        ))}
      </div>
      {accounts.data?.length === 0 && (
        <p className="mt-6">No AWS accounts are available for assessment.</p>
      )}
      <div className="mt-10 flex items-center justify-between">
        <h2 className="text-xl font-bold">Latest assessments</h2>
        <Link className="text-blue-300 underline" to="/compliance/assessments">
          View history
        </Link>
      </div>
      <LoadState
        loading={assessments.isLoading}
        error={assessments.isError}
        label="assessments"
      />
      {assessments.data?.items.length === 0 && (
        <p className="mt-3">No assessments yet.</p>
      )}
      <AssessmentTable
        assessments={assessments.data?.items ?? []}
        frameworks={frameworks.data ?? []}
        accounts={accounts.data ?? []}
      />
    </section>
  );
}

function AssessmentDialog({
  frameworks,
  accounts,
}: {
  frameworks: ComplianceFramework[];
  accounts: AWSAccount[];
}) {
  const organization = useOrganization();
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [accountId, setAccountId] = useState("");
  const [frameworkId, setFrameworkId] = useState("");
  const triggerRef = useRef<HTMLButtonElement>(null);
  const confirmRef = useRef<HTMLButtonElement>(null);
  const selected = frameworks.find((item) => item.id === frameworkId);
  const mutation = useMutation({
    mutationFn: () =>
      api<ComplianceAssessment>(
        `/api/v1/aws/accounts/${accountId}/compliance/assess`,
        {
          method: "POST",
          body: JSON.stringify({
            framework_key: selected?.key,
            framework_version: selected?.version,
          }),
        },
      ),
    onSuccess: async () => {
      setOpen(false);
      await queryClient.invalidateQueries({
        queryKey: ["compliance", organization?.id],
      });
      await queryClient.invalidateQueries({
        queryKey: ["compliance-assessments", organization?.id],
      });
      await queryClient.invalidateQueries({
        queryKey: ["compliance-summary", organization?.id],
      });
      triggerRef.current?.focus();
    },
  });
  const close = () => {
    if (mutation.isPending) return;
    setOpen(false);
    triggerRef.current?.focus();
  };
  useEffect(() => {
    if (!open) return;
    confirmRef.current?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") close();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  });
  const message =
    mutation.error instanceof ApiError
      ? mutation.error.status === 409
        ? "An assessment is already active for this account and framework."
        : mutation.error.status === 403
          ? "You are not authorized to run this assessment."
          : mutation.error.status === 422
            ? "Select valid assessment inputs."
            : "Unable to complete the assessment."
      : "Unable to complete the assessment.";
  return (
    <>
      <button
        ref={triggerRef}
        className="button-primary"
        type="button"
        onClick={() => {
          setAccountId(accounts[0]?.id ?? "");
          setFrameworkId(frameworks[0]?.id ?? "");
          setOpen(true);
        }}
      >
        Run assessment
      </button>
      {open && (
        <div
          aria-labelledby="assessment-dialog-title"
          aria-modal="true"
          className="fixed inset-0 z-50 grid place-items-center bg-slate-950/80 p-4"
          role="dialog"
        >
          <div className="card w-full max-w-lg">
            <h2 id="assessment-dialog-title" className="text-xl font-bold">
              Run compliance assessment
            </h2>
            <p className="mt-2 text-sm text-slate-400">
              CloudOps derives an immutable snapshot from deterministic Stage 4
              evidence. Missing source evidence becomes NOT_ASSESSED, not PASS.
            </p>
            <label className="mt-4 block" htmlFor="assessment-account">
              AWS account
            </label>
            <select
              id="assessment-account"
              className="input mt-1"
              disabled={mutation.isPending}
              value={accountId}
              onChange={(event) => setAccountId(event.target.value)}
            >
              <option value="">Select an account</option>
              {accounts.map((account) => (
                <option key={account.id} value={account.id}>
                  {account.name} ({account.account_id})
                </option>
              ))}
            </select>
            <label className="mt-4 block" htmlFor="assessment-framework">
              Framework and version
            </label>
            <select
              id="assessment-framework"
              className="input mt-1"
              disabled={mutation.isPending}
              value={frameworkId}
              onChange={(event) => setFrameworkId(event.target.value)}
            >
              <option value="">Select a framework</option>
              {frameworks.map((framework) => (
                <option key={framework.id} value={framework.id}>
                  {framework.name} {framework.version}
                </option>
              ))}
            </select>
            {mutation.isError && (
              <p className="mt-3 text-red-300" role="alert">
                {message}
              </p>
            )}
            {mutation.isPending && (
              <p aria-live="polite" className="mt-3">
                Assessment request pending.
              </p>
            )}
            <div className="mt-6 flex justify-end gap-3">
              <button
                className="button-secondary"
                disabled={mutation.isPending}
                type="button"
                onClick={close}
              >
                Cancel
              </button>
              <button
                ref={confirmRef}
                className="button-primary"
                disabled={mutation.isPending || !accountId || !frameworkId}
                type="button"
                onClick={() => {
                  if (!mutation.isPending) mutation.mutate();
                }}
              >
                {mutation.isPending ? "Starting…" : "Confirm assessment"}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

export function ComplianceFrameworkPage() {
  const { frameworkKey = "" } = useParams();
  const organization = useOrganization();
  const [search, setSearch] = useState("");
  const frameworks = useFrameworks();
  const framework = frameworks.data?.find((item) => item.key === frameworkKey);
  const controls = useQuery({
    queryKey: ["compliance-controls", organization?.id, frameworkKey],
    enabled: Boolean(organization && frameworkKey),
    queryFn: () =>
      api<ComplianceControl[]>(
        `/api/v1/compliance/frameworks/${encodeURIComponent(frameworkKey)}/controls?organization_id=${organization!.id}`,
      ),
  });
  const filtered =
    controls.data?.filter((control) =>
      `${control.control_key} ${control.title} ${control.description}`
        .toLowerCase()
        .includes(search.toLowerCase()),
    ) ?? [];
  if (!organization) return <p>No organization selected.</p>;
  return (
    <section>
      <Link className="text-blue-300 underline" to="/compliance">
        ← Compliance
      </Link>
      <h1 className="mt-4 text-3xl font-bold">
        {framework?.name ?? frameworkKey}
      </h1>
      {framework && (
        <>
          <p className="mt-1">Framework version {framework.version}</p>
          <p className="mt-3 text-slate-300">
            CloudOps-authored summary: {framework.description}
          </p>
          <a
            className="mt-3 inline-block text-blue-300 underline"
            href={framework.official_reference}
            rel="noreferrer"
            target="_blank"
          >
            Official reference
          </a>
        </>
      )}
      <label className="mt-6 block max-w-md">
        <span className="label">Search controls</span>
        <input
          className="input"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
        />
      </label>
      <LoadState
        loading={controls.isLoading || frameworks.isLoading}
        error={controls.isError || frameworks.isError}
        label="framework controls"
      />
      {!controls.isLoading && filtered.length === 0 && (
        <p className="mt-4">No controls match the current filters.</p>
      )}
      <div className="mt-5 overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead>
            <tr>
              <th scope="col">Control</th>
              <th scope="col">Title</th>
              <th scope="col">Section</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((control) => (
              <tr className="border-t border-border" key={control.id}>
                <td>
                  <Link
                    className="text-blue-300 underline"
                    to={`/compliance/controls/${control.id}`}
                  >
                    {control.control_key}
                  </Link>
                </td>
                <td>{control.title}</td>
                <td>{control.section ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

export function ComplianceControlPage() {
  const { controlId = "" } = useParams();
  const organization = useOrganization();
  const control = useQuery({
    queryKey: ["compliance-control", organization?.id, controlId],
    enabled: Boolean(organization && controlId),
    queryFn: () =>
      api<ComplianceControl>(
        `/api/v1/compliance/controls/${controlId}?organization_id=${organization!.id}`,
      ),
  });
  const mappings = useQuery({
    queryKey: ["compliance-control-rules", organization?.id, controlId],
    enabled: Boolean(organization && controlId),
    queryFn: () =>
      api<RuleControlMapping[]>(
        `/api/v1/compliance/controls/${controlId}/rules?organization_id=${organization!.id}`,
      ),
  });
  const links = useQuery({
    queryKey: ["compliance-control-findings", organization?.id, controlId],
    enabled: Boolean(organization && controlId),
    queryFn: () =>
      api<ComplianceControlFindings>(
        `/api/v1/compliance/controls/${controlId}/findings?organization_id=${organization!.id}&page_size=25`,
      ),
  });
  const findingQueries = useQueries({
    queries: (links.data?.finding_ids ?? []).map((findingId) => ({
      queryKey: ["finding", organization?.id, findingId],
      queryFn: () =>
        api<Finding>(
          `/api/v1/findings/${findingId}?organization_id=${organization!.id}`,
        ),
      enabled: Boolean(organization),
    })),
  });
  if (!organization) return <p>No organization selected.</p>;
  return (
    <section>
      <Link className="text-blue-300 underline" to="/compliance">
        ← Compliance
      </Link>
      <LoadState
        loading={control.isLoading}
        error={control.isError}
        label="control"
      />
      {control.data && (
        <>
          <h1 className="mt-4 text-3xl font-bold">
            {control.data.control_key}: {control.data.title}
          </h1>
          <p className="mt-3">
            CloudOps-authored description: {control.data.description}
          </p>
          <p className="mt-2 text-sm text-slate-400">
            Historical assessment snapshots preserve the status recorded at
            assessment time.
          </p>
        </>
      )}
      <h2 className="mt-8 text-xl font-bold">Mapped deterministic rules</h2>
      <LoadState
        loading={mappings.isLoading}
        error={mappings.isError}
        label="rule mappings"
      />
      {mappings.data?.length === 0 && <p>No mapped rules.</p>}
      <ul className="mt-3 grid gap-3">
        {mappings.data?.map((mapping) => (
          <li className="card" key={mapping.id}>
            <code>{mapping.rule_key}</code>
            <p>
              Versions {mapping.minimum_rule_version}–
              {mapping.maximum_rule_version ?? "latest"}
            </p>
            <p className="text-sm text-slate-400">
              Mapping rationale: {mapping.rationale}
            </p>
          </li>
        ))}
      </ul>
      <h2 className="mt-8 text-xl font-bold">Mapped findings</h2>
      <LoadState
        loading={
          links.isLoading || findingQueries.some((item) => item.isLoading)
        }
        error={links.isError || findingQueries.some((item) => item.isError)}
        label="mapped findings"
      />
      {links.data?.finding_ids.length === 0 && <p>No mapped findings.</p>}
      <ul className="mt-3 grid gap-3">
        {findingQueries.map(
          (query) =>
            query.data && (
              <li className="card" key={query.data.id}>
                <Link
                  className="text-blue-300 underline"
                  to={`/findings/${query.data.id}`}
                >
                  {query.data.rule_key}
                </Link>
                <p>
                  Severity: {query.data.severity}; Service: {query.data.service}
                  ; Region: {query.data.region ?? "global"}
                </p>
                <StatusText value={query.data.status} />
              </li>
            ),
        )}
      </ul>
    </section>
  );
}

export function ComplianceAssessmentsPage() {
  const organization = useOrganization();
  const frameworks = useFrameworks();
  const accounts = useAccounts();
  const [page, setPage] = useState(1);
  const [filters, setFilters] = useState({
    framework_key: "",
    framework_version: "",
    aws_account_id: "",
    assessment_status: "",
  });
  const queryString = useMemo(() => {
    const params = new URLSearchParams({
      organization_id: organization?.id ?? "",
      page: String(page),
      page_size: "10",
    });
    Object.entries(filters).forEach(
      ([key, value]) => value && params.set(key, value),
    );
    return params.toString();
  }, [filters, organization?.id, page]);
  const assessments = useQuery({
    queryKey: ["compliance-assessments", organization?.id, queryString],
    enabled: Boolean(organization),
    queryFn: () =>
      api<Page<ComplianceAssessment>>(
        `/api/v1/compliance/assessments?${queryString}`,
      ),
  });
  const update = (key: keyof typeof filters, value: string) => {
    setPage(1);
    setFilters((current) => ({ ...current, [key]: value }));
  };
  if (!organization) return <p>No organization selected.</p>;
  return (
    <section>
      <h1 className="text-3xl font-bold">Compliance assessments</h1>
      <div className="card mt-5 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        <Select
          label="AWS account"
          value={filters.aws_account_id}
          onChange={(value) => update("aws_account_id", value)}
        >
          {accounts.data?.map((account) => (
            <option key={account.id} value={account.id}>
              {account.name}
            </option>
          ))}
        </Select>
        <Select
          label="Framework"
          value={filters.framework_key}
          onChange={(value) => update("framework_key", value)}
        >
          {frameworks.data?.map((framework) => (
            <option key={framework.id} value={framework.key}>
              {framework.name}
            </option>
          ))}
        </Select>
        <Select
          label="Framework version"
          value={filters.framework_version}
          onChange={(value) => update("framework_version", value)}
        >
          {[...new Set(frameworks.data?.map((item) => item.version))].map(
            (version) => (
              <option key={version} value={version}>
                {version}
              </option>
            ),
          )}
        </Select>
        <Select
          label="Assessment status"
          value={filters.assessment_status}
          onChange={(value) => update("assessment_status", value)}
        >
          {["pending", "running", "completed", "failed"].map((status) => (
            <option key={status} value={status}>
              {status}
            </option>
          ))}
        </Select>
      </div>
      <LoadState
        loading={assessments.isLoading}
        error={assessments.isError}
        label="assessment history"
      />
      {assessments.data?.items.length === 0 && (
        <p className="mt-4">No assessments match the current filters.</p>
      )}
      <AssessmentTable
        assessments={assessments.data?.items ?? []}
        frameworks={frameworks.data ?? []}
        accounts={accounts.data ?? []}
      />
      <Pagination
        page={page}
        total={assessments.data?.total ?? 0}
        pageSize={10}
        setPage={setPage}
      />
    </section>
  );
}

export function ComplianceAssessmentPage() {
  const { assessmentId = "" } = useParams();
  const organization = useOrganization();
  const [status, setStatus] = useState("");
  const assessment = useQuery({
    queryKey: ["compliance-assessment", organization?.id, assessmentId],
    enabled: Boolean(organization && assessmentId),
    queryFn: () =>
      api<ComplianceAssessment & { controls: ComplianceAssessmentControl[] }>(
        `/api/v1/compliance/assessments/${assessmentId}?organization_id=${organization!.id}`,
      ),
  });
  if (!organization) return <p>No organization selected.</p>;
  const controls =
    assessment.data?.controls.filter(
      (item) => !status || item.status === status,
    ) ?? [];
  return (
    <section>
      <Link className="text-blue-300 underline" to="/compliance/assessments">
        ← Assessment history
      </Link>
      <h1 className="mt-4 text-3xl font-bold">
        Historical compliance assessment
      </h1>
      <LoadState
        loading={assessment.isLoading}
        error={assessment.isError}
        label="assessment"
      />
      {assessment.data && (
        <>
          <div className="card mt-5">
            <StatusText value={assessment.data.status} />
            <p className="mt-3">
              Source evaluation:{" "}
              {assessment.data.evaluation_job_id ?? "No completed evaluation"}
            </p>
            <p>Started: {formatDate(assessment.data.started_at)}</p>
            <p>Finished: {formatDate(assessment.data.finished_at)}</p>
            {assessment.data.error_summary && (
              <p role="alert">
                Assessment error: {assessment.data.error_summary}
              </p>
            )}
            <p className="mt-3 text-sm text-slate-400">
              This immutable snapshot does not change when findings are later
              resolved, suppressed, or reopened.
            </p>
          </div>
          <CounterGrid
            summary={{
              assessments_total: 1,
              controls_passed: assessment.data.controls_passed,
              controls_failed: assessment.data.controls_failed,
              controls_not_assessed: assessment.data.controls_not_assessed,
              controls_error: assessment.data.controls_error,
            }}
          />
          <div className="mt-5">
            <AIWorkflow
              organization={organization}
              sourceType="compliance_assessment"
              sourceId={assessment.data.id}
              tasks={["executive_summary", "email_summary"]}
            />
          </div>
          <Select label="Control status" value={status} onChange={setStatus}>
            {controlStatuses.map((item) => (
              <option key={item} value={item}>
                {item.replaceAll("_", " ")}
              </option>
            ))}
          </Select>
          <div className="mt-5 overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead>
                <tr>
                  <th scope="col">Control</th>
                  <th scope="col">Status</th>
                  <th scope="col">Findings</th>
                  <th scope="col">Snapshot time</th>
                </tr>
              </thead>
              <tbody>
                {controls.map((snapshot) => (
                  <tr className="border-t border-border" key={snapshot.id}>
                    <td>
                      <Link
                        className="text-blue-300 underline"
                        to={`/compliance/controls/${snapshot.control_id}`}
                      >
                        {snapshot.control_id}
                      </Link>
                    </td>
                    <td>
                      <StatusText value={snapshot.status} />
                    </td>
                    <td>{snapshot.findings_count}</td>
                    <td>{formatDate(snapshot.assessed_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </section>
  );
}

function AssessmentTable({
  assessments,
  frameworks,
  accounts,
}: {
  assessments: ComplianceAssessment[];
  frameworks: ComplianceFramework[];
  accounts: AWSAccount[];
}) {
  return (
    <div className="mt-4 overflow-x-auto">
      <table className="w-full text-left text-sm">
        <thead>
          <tr>
            <th scope="col">Status</th>
            <th scope="col">AWS account</th>
            <th scope="col">Framework</th>
            <th scope="col">Started</th>
            <th scope="col">PASS</th>
            <th scope="col">FAIL</th>
            <th scope="col">NOT_ASSESSED</th>
            <th scope="col">ERROR</th>
          </tr>
        </thead>
        <tbody>
          {assessments.map((assessment) => {
            const framework = frameworks.find(
              (item) => item.id === assessment.framework_id,
            );
            const account = accounts.find(
              (item) => item.id === assessment.aws_account_id,
            );
            return (
              <tr className="border-t border-border" key={assessment.id}>
                <td>
                  <Link to={`/compliance/assessments/${assessment.id}`}>
                    <StatusText value={assessment.status} />
                  </Link>
                </td>
                <td>
                  {account?.name ?? assessment.aws_account_id ?? "Organization"}
                </td>
                <td>
                  {framework
                    ? `${framework.name} ${framework.version}`
                    : assessment.framework_id}
                </td>
                <td>{formatDate(assessment.started_at)}</td>
                <td>{assessment.controls_passed}</td>
                <td>{assessment.controls_failed}</td>
                <td>{assessment.controls_not_assessed}</td>
                <td>{assessment.controls_error}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function Select({
  label,
  value,
  onChange,
  children,
}: {
  label: string;
  value: string;
  onChange(value: string): void;
  children: ReactNode;
}) {
  return (
    <label className="block">
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
  setPage,
}: {
  page: number;
  total: number;
  pageSize: number;
  setPage(value: number): void;
}) {
  return (
    <nav
      aria-label="Assessment pagination"
      className="mt-5 flex items-center gap-3"
    >
      <button
        aria-label="Previous assessment page"
        className="button-secondary"
        disabled={page === 1}
        type="button"
        onClick={() => setPage(page - 1)}
      >
        Previous
      </button>
      <span>Page {page}</span>
      <button
        aria-label="Next assessment page"
        className="button-secondary"
        disabled={page * pageSize >= total}
        type="button"
        onClick={() => setPage(page + 1)}
      >
        Next
      </button>
    </nav>
  );
}

function formatDate(value: string | null) {
  return value ? new Date(value).toLocaleString() : "—";
}
