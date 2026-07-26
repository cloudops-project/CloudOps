import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, apiBlob, ApiError } from "../api/client";
import { useAuth } from "../auth/AuthProvider";
import type { AuditEvent, AuditResult, Page } from "../types";

const readRoles = ["owner", "admin", "auditor"];
const results: Array<AuditResult | ""> = ["", "succeeded", "failed", "denied"];

function ResultBadge({ result }: { result: string }) {
  const tone =
    result === "failed" || result === "denied"
      ? "text-red-300"
      : "text-slate-300";
  return <span className={`uppercase ${tone}`}>{result}</span>;
}

export function AuditPage() {
  const organization = useAuth().me?.organizations[0];
  const [page, setPage] = useState(1);
  const [filters, setFilters] = useState({
    event_type: "",
    resource_type: "",
    result: "",
    start_time: "",
    end_time: "",
  });
  const [exportError, setExportError] = useState<string | null>(null);
  const [exporting, setExporting] = useState(false);

  const canRead = Boolean(
    organization && readRoles.includes(organization.role),
  );

  const queryString = () => {
    const params = new URLSearchParams({
      organization_id: organization!.id,
      page: String(page),
      page_size: "25",
    });
    if (filters.event_type) params.set("event_type", filters.event_type);
    if (filters.resource_type)
      params.set("resource_type", filters.resource_type);
    if (filters.result) params.set("result", filters.result);
    if (filters.start_time)
      params.set("start_time", new Date(filters.start_time).toISOString());
    if (filters.end_time)
      params.set("end_time", new Date(filters.end_time).toISOString());
    return params.toString();
  };

  const events = useQuery({
    queryKey: ["audit-events", organization?.id, filters, page],
    enabled: Boolean(organization) && canRead,
    queryFn: () =>
      api<Page<AuditEvent>>(`/api/v1/audit-events?${queryString()}`),
  });

  const update = (key: keyof typeof filters, value: string) => {
    setPage(1);
    setFilters((current) => ({ ...current, [key]: value }));
  };

  const exportCsv = async () => {
    if (!organization) return;
    setExporting(true);
    setExportError(null);
    try {
      const blob = await apiBlob(
        `/api/v1/audit-events/export?${queryString()}`,
      );
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = "audit-events.csv";
      link.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      setExportError(
        err instanceof ApiError
          ? err.message
          : "Unable to export audit events.",
      );
    } finally {
      setExporting(false);
    }
  };

  if (!organization) return <p>No organization selected.</p>;
  if (!canRead) {
    return (
      <section>
        <h1 className="text-3xl font-bold">Audit log</h1>
        <p className="mt-3 text-slate-400">
          You do not have access to the audit log for this organization.
        </p>
      </section>
    );
  }

  return (
    <section aria-labelledby="audit-title">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 id="audit-title" className="text-3xl font-bold">
            Audit log
          </h1>
          <p className="mt-2 text-slate-400">
            Every recorded security-relevant action for this organization.
            Export produces a CSV of up to 5,000 matching rows for the current
            filters.
          </p>
        </div>
        <button
          className="button"
          disabled={exporting}
          onClick={() => void exportCsv()}
        >
          {exporting ? "Exporting…" : "Export CSV"}
        </button>
      </div>
      {exportError && (
        <p role="alert" className="mt-2 text-sm text-red-300">
          {exportError}
        </p>
      )}
      <div className="card my-5 grid gap-3 md:grid-cols-3 xl:grid-cols-5">
        <label>
          <span className="label">Event type</span>
          <input
            className="input"
            value={filters.event_type}
            onChange={(event) => update("event_type", event.target.value)}
          />
        </label>
        <label>
          <span className="label">Resource type</span>
          <input
            className="input"
            value={filters.resource_type}
            onChange={(event) => update("resource_type", event.target.value)}
          />
        </label>
        <label>
          <span className="label">Result</span>
          <select
            className="input"
            value={filters.result}
            onChange={(event) => update("result", event.target.value)}
          >
            {results.map((item) => (
              <option key={item || "all"} value={item}>
                {item ? item : "All results"}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span className="label">Since</span>
          <input
            className="input"
            type="datetime-local"
            value={filters.start_time}
            onChange={(event) => update("start_time", event.target.value)}
          />
        </label>
        <label>
          <span className="label">Until</span>
          <input
            className="input"
            type="datetime-local"
            value={filters.end_time}
            onChange={(event) => update("end_time", event.target.value)}
          />
        </label>
      </div>
      {events.isLoading && <p aria-live="polite">Loading audit events…</p>}
      {events.isError && <p role="alert">Unable to load audit events.</p>}
      {events.data?.items.length === 0 && (
        <p className="mt-5">No audit events match these filters.</p>
      )}
      {Boolean(events.data?.items.length) && (
        <div className="mt-5 overflow-x-auto">
          <table className="w-full text-left">
            <thead>
              <tr>
                <th className="px-3 py-2">Event</th>
                <th className="px-3 py-2">Resource</th>
                <th className="px-3 py-2">Result</th>
                <th className="px-3 py-2">Actor</th>
                <th className="px-3 py-2">Created</th>
              </tr>
            </thead>
            <tbody>
              {events.data?.items.map((item) => (
                <tr key={item.id}>
                  <td className="px-3 py-3 font-mono text-sm">
                    {item.event_type}
                  </td>
                  <td className="px-3 py-3">{item.resource_type}</td>
                  <td className="px-3 py-3">
                    <ResultBadge result={item.result} />
                  </td>
                  <td className="px-3 py-3">
                    {item.actor_user_id ?? "System"}
                  </td>
                  <td className="px-3 py-3">
                    {new Date(item.created_at).toLocaleString()}
                  </td>
                </tr>
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
          disabled={page * 25 >= (events.data?.total ?? 0)}
          onClick={() => setPage((value) => value + 1)}
        >
          Next
        </button>
      </div>
    </section>
  );
}
