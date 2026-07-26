import { useQuery } from "@tanstack/react-query";
import {
  AlertTriangle,
  Boxes,
  Cloud,
  Gauge,
  RefreshCw,
  Scale,
  ShieldAlert,
} from "lucide-react";
import { Link } from "react-router";
import { api } from "../api/client";
import { useAuth } from "../auth/AuthProvider";
import type { DashboardCountItem, DashboardSummary } from "../types";

function Bar({ items, total }: { items: DashboardCountItem[]; total: number }) {
  if (items.length === 0) {
    return <p className="text-sm text-slate-400">No data.</p>;
  }
  return (
    <ul className="grid gap-2">
      {items.map((item) => {
        const pct = total > 0 ? Math.round((item.count / total) * 100) : 0;
        return (
          <li key={item.key}>
            <div className="flex justify-between text-sm">
              <span className="capitalize">
                {item.key.replaceAll("_", " ")}
              </span>
              <span className="text-slate-400">{item.count}</span>
            </div>
            <div
              className="mt-1 h-2 w-full rounded-full bg-slate-800"
              role="img"
              aria-label={`${item.key.replaceAll("_", " ")}: ${item.count} of ${total}, ${pct}%`}
            >
              <div
                className="h-2 rounded-full bg-blue-500"
                style={{ width: `${pct}%` }}
              />
            </div>
          </li>
        );
      })}
    </ul>
  );
}

function StatCard({
  label,
  value,
  sub,
}: {
  label: string;
  value: string | number;
  sub?: string;
}) {
  return (
    <article className="card">
      <p className="text-sm text-slate-400">{label}</p>
      <p className="mt-2 text-3xl font-extrabold">{value}</p>
      {sub && <p className="mt-1 text-sm text-slate-400">{sub}</p>}
    </article>
  );
}

export function SecurityDashboardPage() {
  const organization = useAuth().me?.organizations[0];
  const summary = useQuery({
    queryKey: ["dashboard-summary", organization?.id],
    enabled: Boolean(organization),
    queryFn: () =>
      api<DashboardSummary>(
        `/api/v1/dashboard/summary?organization_id=${organization!.id}`,
      ),
  });

  if (!organization) {
    return (
      <section className="card text-center">
        <h1 className="text-3xl font-bold">No organization selected</h1>
        <p className="my-4 text-slate-400">
          Select or create an organization to view its security posture.
        </p>
        <Link className="button" to="/organizations/new">
          Create organization
        </Link>
      </section>
    );
  }

  if (summary.isLoading) {
    return (
      <p aria-live="polite" className="mt-5">
        Loading security posture…
      </p>
    );
  }

  if (summary.isError) {
    return (
      <section aria-labelledby="security-dashboard-error-title">
        <h1 id="security-dashboard-error-title" className="text-3xl font-bold">
          Security posture
        </h1>
        <p role="alert" className="mt-4 text-red-400">
          Unable to load the security dashboard.
        </p>
        <button
          className="button-secondary mt-4 inline-flex items-center gap-2"
          onClick={() => void summary.refetch()}
        >
          <RefreshCw size={16} />
          Retry
        </button>
      </section>
    );
  }

  const data = summary.data;
  if (!data) return null;

  return (
    <section aria-labelledby="security-dashboard-title">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 id="security-dashboard-title" className="text-3xl font-bold">
            Security posture
          </h1>
          <p className="mt-2 text-slate-400">
            Organization-wide summary derived from persisted Stage 2-7 records.
            No live AWS or AI calls are made to render this page.
          </p>
        </div>
        <button
          className="button-secondary inline-flex items-center gap-2"
          onClick={() => void summary.refetch()}
        >
          <RefreshCw size={16} />
          Refresh
        </button>
      </div>

      {data.metadata.is_partial && (
        <p
          role="status"
          className="mt-4 rounded-button border border-amber-600 bg-amber-950/40 px-4 py-3 text-amber-200"
        >
          This dashboard is showing partial data. Missing sections:{" "}
          {data.metadata.missing_sections.length > 0
            ? data.metadata.missing_sections
                .map((section) => section.replaceAll("_", " "))
                .join(", ")
            : "none"}
        </p>
      )}

      <div className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          label="Connected accounts"
          value={data.accounts.connected_accounts}
          sub={`${data.accounts.total_accounts} total`}
        />
        <StatCard
          label="Accounts needing attention"
          value={data.accounts.accounts_requiring_attention}
        />
        <StatCard
          label="Active assets"
          value={data.assets.active_assets}
          sub={`${data.assets.total_assets} total`}
        />
        <StatCard
          label="Open findings"
          value={data.findings.open_total}
          sub={`${data.findings.resolved_total} resolved, ${data.findings.suppressed_total} suppressed`}
        />
      </div>

      <div className="mt-6 grid gap-4 lg:grid-cols-2">
        <section className="card" aria-labelledby="asset-distribution-title">
          <div className="mb-4 flex items-center gap-2">
            <Boxes className="text-blue-400" />
            <h2 id="asset-distribution-title" className="text-xl font-bold">
              Asset distribution
            </h2>
          </div>
          <p className="mb-2 text-sm text-slate-400">By type</p>
          <Bar
            items={data.assets.counts_by_type}
            total={data.assets.total_assets}
          />
          <p className="mb-2 mt-4 text-sm text-slate-400">By region</p>
          <Bar
            items={data.assets.counts_by_region}
            total={data.assets.total_assets}
          />
        </section>

        <section className="card" aria-labelledby="finding-distribution-title">
          <div className="mb-4 flex items-center gap-2">
            <ShieldAlert className="text-blue-400" />
            <h2 id="finding-distribution-title" className="text-xl font-bold">
              Open findings
            </h2>
          </div>
          <p className="mb-2 text-sm text-slate-400">By severity</p>
          <Bar
            items={data.findings.open_by_severity}
            total={data.findings.open_total}
          />
          <p className="mb-2 mt-4 text-sm text-slate-400">By service</p>
          <Bar
            items={data.findings.open_by_service}
            total={data.findings.open_total}
          />
        </section>
      </div>

      <section className="card mt-6" aria-labelledby="recent-findings-title">
        <div className="mb-4 flex items-center gap-2">
          <AlertTriangle className="text-blue-400" />
          <h2 id="recent-findings-title" className="text-xl font-bold">
            Recent critical and high findings
          </h2>
        </div>
        {data.findings.recent_critical_and_high_findings.length === 0 ? (
          <p className="text-slate-400">
            No open critical or high severity findings.
          </p>
        ) : (
          <ul className="grid gap-3">
            {data.findings.recent_critical_and_high_findings.map((finding) => (
              <li
                key={finding.id}
                className="flex flex-wrap items-center justify-between gap-2 border-b border-border pb-3"
              >
                <Link
                  className="text-blue-300 underline"
                  to={`/findings/${finding.id}`}
                >
                  {finding.rule_key}
                </Link>
                <span className="text-sm uppercase text-slate-400">
                  {finding.severity}
                </span>
                <span className="text-sm text-slate-400">
                  {finding.service}
                  {finding.region ? ` · ${finding.region}` : ""}
                </span>
                <time className="text-sm text-slate-400">
                  {new Date(finding.last_seen_at).toLocaleString()}
                </time>
              </li>
            ))}
          </ul>
        )}
        <Link
          className="mt-5 inline-flex items-center gap-2 text-blue-400"
          to="/findings"
        >
          View all findings
        </Link>
      </section>

      <div className="mt-6 grid gap-4 lg:grid-cols-2">
        <section className="card" aria-labelledby="compliance-summary-title">
          <div className="mb-4 flex items-center gap-2">
            <Scale className="text-blue-400" />
            <h2 id="compliance-summary-title" className="text-xl font-bold">
              Compliance
            </h2>
          </div>
          {data.compliance.assessment_id === null ? (
            <p className="text-slate-400">
              No completed compliance assessment.
            </p>
          ) : (
            <>
              <p className="text-3xl font-extrabold">
                {data.compliance.pass_percentage === null
                  ? "—"
                  : `${data.compliance.pass_percentage}%`}
              </p>
              <p className="text-sm text-slate-400">
                {data.compliance.framework_name} v
                {data.compliance.framework_version}
              </p>
              <p className="mt-2 text-sm text-slate-400">
                {data.compliance.passed} passed, {data.compliance.failed}{" "}
                failed, {data.compliance.not_assessed} not assessed
              </p>
            </>
          )}
          <Link
            className="mt-5 inline-flex items-center gap-2 text-blue-400"
            to="/compliance"
          >
            View compliance
          </Link>
        </section>

        <section className="card" aria-labelledby="risk-summary-title">
          <div className="mb-4 flex items-center gap-2">
            <Gauge className="text-blue-400" />
            <h2 id="risk-summary-title" className="text-xl font-bold">
              Risk
            </h2>
          </div>
          {data.risk.assessment_id === null ? (
            <p className="text-slate-400">No completed risk assessment.</p>
          ) : (
            <>
              <p className="text-3xl font-extrabold">
                {data.risk.aggregate_score ?? "—"}
              </p>
              <p className="text-sm uppercase text-slate-400">
                {data.risk.aggregate_priority ?? "unknown"}
              </p>
              {data.risk.trend.length > 0 && (
                <p
                  className="mt-2 text-sm text-slate-400"
                  aria-label={`Risk trend: ${data.risk.trend
                    .map((point) => point.aggregate_score)
                    .join(", then ")}`}
                >
                  Trend:{" "}
                  {data.risk.trend
                    .map((point) => point.aggregate_score)
                    .join(" → ")}
                </p>
              )}
            </>
          )}
          <Link
            className="mt-5 inline-flex items-center gap-2 text-blue-400"
            to="/risk"
          >
            View risk
          </Link>
        </section>
      </div>

      {data.account_risk_heatmap.length > 0 && (
        <section className="card mt-6" aria-labelledby="account-heatmap-title">
          <div className="mb-4 flex items-center gap-2">
            <Cloud className="text-blue-400" />
            <h2 id="account-heatmap-title" className="text-xl font-bold">
              Account risk heatmap
            </h2>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-left">
              <thead>
                <tr>
                  <th className="px-3 py-2">Account</th>
                  <th className="px-3 py-2">Score</th>
                  <th className="px-3 py-2">Priority</th>
                  <th className="px-3 py-2">Critical</th>
                  <th className="px-3 py-2">High</th>
                </tr>
              </thead>
              <tbody>
                {data.account_risk_heatmap.map((item) => (
                  <tr key={item.aws_account_id}>
                    <td className="px-3 py-2">
                      {item.account_display_identifier}
                    </td>
                    <td className="px-3 py-2">{item.score}</td>
                    <td className="px-3 py-2 uppercase">{item.priority}</td>
                    <td className="px-3 py-2">{item.critical_count}</td>
                    <td className="px-3 py-2">{item.high_count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      <section className="card mt-6" aria-labelledby="freshness-title">
        <h2 id="freshness-title" className="text-xl font-bold">
          Operational freshness
        </h2>
        <dl className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {(
            [
              ["Last discovery", data.freshness.latest_completed_discovery],
              ["Last evaluation", data.freshness.latest_completed_evaluation],
              [
                "Last compliance assessment",
                data.freshness.latest_completed_compliance_assessment,
              ],
              [
                "Last risk assessment",
                data.freshness.latest_completed_risk_assessment,
              ],
            ] as const
          ).map(([label, item]) => (
            <div key={label}>
              <dt className="text-sm text-slate-400">{label}</dt>
              <dd className="mt-1 font-semibold">
                {item?.finished_at
                  ? new Date(item.finished_at).toLocaleString()
                  : "Not yet run"}
              </dd>
            </div>
          ))}
        </dl>
      </section>
    </section>
  );
}
