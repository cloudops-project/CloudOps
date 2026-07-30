import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, ApiError } from "../api/client";
import { useAuth } from "../auth/AuthProvider";
import type { Page, RemediationRequest, RemediationStatus } from "../types";

const approveRoles = ["owner", "admin", "security_analyst"];
const requestRoles = ["owner", "admin", "security_analyst", "cloud_engineer"];
const statuses: Array<RemediationStatus | ""> = [
  "",
  "pending_approval",
  "approved",
  "rejected",
  "cancelled",
  "succeeded",
  "failed",
];

function StatusBadge({ status }: { status: RemediationStatus }) {
  return (
    <span className="inline-flex items-center gap-2 rounded-full border border-slate-600 px-3 py-1 uppercase">
      {status.replace("_", " ")}
    </span>
  );
}

function RemediationRow({
  item,
  organizationId,
  mayApprove,
  mayReject,
  mayExecute,
  mayCancel,
}: {
  item: RemediationRequest;
  organizationId: string;
  mayApprove: boolean;
  mayReject: boolean;
  mayExecute: boolean;
  mayCancel: boolean;
}) {
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const [rejectOpen, setRejectOpen] = useState(false);
  const [reason, setReason] = useState("");

  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: ["remediations"] });

  const approve = useMutation({
    mutationFn: () =>
      api<RemediationRequest>(
        `/api/v1/remediations/${item.id}/approve?organization_id=${organizationId}`,
        { method: "POST" },
      ),
    onSuccess: async () => {
      setError(null);
      await invalidate();
    },
    onError: (err: unknown) => {
      setError(
        err instanceof ApiError ? err.message : "Approval failed safely.",
      );
    },
  });
  const reject = useMutation({
    mutationFn: () =>
      api<RemediationRequest>(
        `/api/v1/remediations/${item.id}/reject?organization_id=${organizationId}`,
        { method: "POST", body: JSON.stringify({ reason }) },
      ),
    onSuccess: async () => {
      setError(null);
      setRejectOpen(false);
      setReason("");
      await invalidate();
    },
    onError: (err: unknown) => {
      setError(
        err instanceof ApiError ? err.message : "Rejection failed safely.",
      );
    },
  });
  const cancel = useMutation({
    mutationFn: () =>
      api<RemediationRequest>(
        `/api/v1/remediations/${item.id}/cancel?organization_id=${organizationId}`,
        { method: "POST" },
      ),
    onSuccess: async () => {
      setError(null);
      await invalidate();
    },
    onError: (err: unknown) => {
      setError(
        err instanceof ApiError ? err.message : "Cancellation failed safely.",
      );
    },
  });
  const execute = useMutation({
    mutationFn: () =>
      api<RemediationRequest>(
        `/api/v1/remediations/${item.id}/execute?organization_id=${organizationId}`,
        { method: "POST" },
      ),
    onSuccess: async () => {
      setError(null);
      await invalidate();
    },
    onError: (err: unknown) => {
      setError(
        err instanceof ApiError ? err.message : "Execution failed safely.",
      );
    },
  });

  const busy =
    approve.isPending ||
    reject.isPending ||
    cancel.isPending ||
    execute.isPending;
  const terminal =
    item.status === "rejected" ||
    item.status === "cancelled" ||
    item.status === "succeeded" ||
    item.status === "failed";

  return (
    <tr>
      <td className="px-3 py-3">{item.title}</td>
      <td className="px-3 py-3">{item.rule_key}</td>
      <td className="px-3 py-3">
        <div className="flex flex-wrap items-center gap-2">
          <StatusBadge status={item.status} />
          {/* Makes the safe execution state visible rather than implied. */}
          {item.dry_run && (
            <span
              className="rounded border border-emerald-700 px-2 py-0.5 text-xs text-emerald-300"
              title="Simulated only. No AWS resource is modified."
            >
              Dry run
            </span>
          )}
          {item.execution_mode === "mock_automation" && (
            <span className="text-xs text-slate-400">mock automation</span>
          )}
        </div>
      </td>
      <td className="px-3 py-3">{item.attempt_count}</td>
      <td className="px-3 py-3">
        {new Date(item.requested_at).toLocaleString()}
      </td>
      <td className="px-3 py-3">
        <div className="flex flex-wrap gap-2">
          {mayApprove && item.status === "pending_approval" && (
            <button
              className="button-primary"
              disabled={busy}
              onClick={() => approve.mutate()}
            >
              {approve.isPending ? "Approving…" : "Approve"}
            </button>
          )}
          {mayReject && item.status === "pending_approval" && (
            <button
              className="button-secondary"
              disabled={busy}
              onClick={() => setRejectOpen(true)}
            >
              Reject
            </button>
          )}
          {mayExecute && item.status === "approved" && (
            <button
              className="button-primary"
              disabled={busy}
              onClick={() => execute.mutate()}
            >
              {execute.isPending ? "Executing…" : "Execute"}
            </button>
          )}
          {mayCancel &&
            (item.status === "pending_approval" ||
              item.status === "approved") && (
              <button
                className="button-secondary"
                disabled={busy}
                onClick={() => cancel.mutate()}
              >
                {cancel.isPending ? "Cancelling…" : "Cancel"}
              </button>
            )}
          {item.status === "succeeded" && (
            <span className="text-slate-400">Succeeded</span>
          )}
          {item.status === "failed" && (
            <span className="text-red-300">
              Failed{item.failure_reason ? `: ${item.failure_reason}` : ""}
            </span>
          )}
          {item.status === "rejected" && (
            <span className="text-slate-400">
              Rejected
              {item.rejection_reason ? `: ${item.rejection_reason}` : ""}
            </span>
          )}
          {item.status === "cancelled" && (
            <span className="text-slate-400">Cancelled</span>
          )}
        </div>
        {error && (
          <p role="alert" className="mt-1 text-sm text-red-300">
            {error}
          </p>
        )}
        {rejectOpen && !terminal && (
          <div className="mt-2 grid gap-2">
            <label>
              <span className="label">Rejection reason</span>
              <textarea
                className="input min-h-16"
                value={reason}
                onChange={(event) => setReason(event.target.value)}
              />
            </label>
            <div className="flex gap-2">
              <button
                className="button-secondary"
                onClick={() => {
                  setRejectOpen(false);
                  setReason("");
                }}
              >
                Cancel
              </button>
              <button
                className="button"
                disabled={reason.trim().length < 3 || reject.isPending}
                onClick={() => reject.mutate()}
              >
                {reject.isPending ? "Rejecting…" : "Confirm reject"}
              </button>
            </div>
          </div>
        )}
      </td>
    </tr>
  );
}

export function RemediationsPage() {
  const organization = useAuth().me?.organizations[0];
  const [status, setStatus] = useState<RemediationStatus | "">("");
  const [page, setPage] = useState(1);
  const remediations = useQuery({
    queryKey: ["remediations", organization?.id, status, page],
    enabled: Boolean(organization),
    queryFn: () => {
      const params = new URLSearchParams({
        organization_id: organization!.id,
        page: String(page),
        page_size: "10",
      });
      if (status) params.set("status", status);
      return api<Page<RemediationRequest>>(`/api/v1/remediations?${params}`);
    },
  });
  if (!organization) return <p>No organization selected.</p>;
  const role = organization.role;
  const mayApprove = approveRoles.includes(role);
  const mayReject = approveRoles.includes(role);
  const mayExecute = approveRoles.includes(role);
  const mayCancel = requestRoles.includes(role);
  return (
    <section aria-labelledby="remediations-title">
      <div>
        <h1 id="remediations-title" className="text-3xl font-bold">
          Remediation
        </h1>
        <p className="mt-2 text-slate-400">
          Proposed remediations require approval before execution. Execution
          uses a deterministic mock automation provider only — no real AWS
          resources are changed.
        </p>
      </div>
      <div className="mt-8 flex flex-wrap gap-3">
        <label>
          Status
          <select
            className="input mt-1 block"
            value={status}
            onChange={(event) => {
              setStatus(event.target.value as RemediationStatus | "");
              setPage(1);
            }}
          >
            {statuses.map((item) => (
              <option key={item || "all"} value={item}>
                {item ? item.replace("_", " ") : "All statuses"}
              </option>
            ))}
          </select>
        </label>
      </div>
      {remediations.isLoading && (
        <p aria-live="polite">Loading remediation requests…</p>
      )}
      {remediations.isError && (
        <p role="alert">Unable to load remediation requests.</p>
      )}
      {remediations.data?.items.length === 0 && (
        <p className="mt-5">No remediation requests.</p>
      )}
      {Boolean(remediations.data?.items.length) && (
        <div className="mt-5 overflow-x-auto">
          <table className="w-full text-left">
            <thead>
              <tr>
                <th className="px-3 py-2">Title</th>
                <th className="px-3 py-2">Rule</th>
                <th className="px-3 py-2">Status</th>
                <th className="px-3 py-2">Attempts</th>
                <th className="px-3 py-2">Requested</th>
                <th className="px-3 py-2">Action</th>
              </tr>
            </thead>
            <tbody>
              {remediations.data?.items.map((item) => (
                <RemediationRow
                  key={item.id}
                  item={item}
                  organizationId={organization.id}
                  mayApprove={mayApprove}
                  mayReject={mayReject}
                  mayExecute={mayExecute}
                  mayCancel={mayCancel}
                />
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
          disabled={page * 10 >= (remediations.data?.total ?? 0)}
          onClick={() => setPage((value) => value + 1)}
        >
          Next
        </button>
      </div>
    </section>
  );
}
