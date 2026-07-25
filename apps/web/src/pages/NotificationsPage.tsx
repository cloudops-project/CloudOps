import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, ApiError } from "../api/client";
import { useAuth } from "../auth/AuthProvider";
import type { NotificationEvent, NotificationStatus, Page } from "../types";

const approveRoles = ["owner", "admin", "security_analyst"];
const statuses: Array<NotificationStatus | ""> = [
  "",
  "pending_approval",
  "approved",
  "delivered",
  "failed",
];

function StatusBadge({ status }: { status: NotificationStatus }) {
  return (
    <span className="inline-flex items-center gap-2 rounded-full border border-slate-600 px-3 py-1 uppercase">
      {status.replace("_", " ")}
    </span>
  );
}

function NotificationRow({
  item,
  organizationId,
  mayApprove,
}: {
  item: NotificationEvent;
  organizationId: string;
  mayApprove: boolean;
}) {
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const approve = useMutation({
    mutationFn: () =>
      api<NotificationEvent>(
        `/api/v1/notifications/${item.id}/approve?organization_id=${organizationId}`,
        { method: "POST" },
      ),
    onSuccess: async () => {
      setError(null);
      await queryClient.invalidateQueries({ queryKey: ["notifications"] });
    },
    onError: (err: unknown) => {
      setError(
        err instanceof ApiError ? err.message : "Approval failed safely.",
      );
    },
  });
  const deliver = useMutation({
    mutationFn: () =>
      api<NotificationEvent>(
        `/api/v1/notifications/${item.id}/deliver?organization_id=${organizationId}`,
        { method: "POST" },
      ),
    onSuccess: async () => {
      setError(null);
      await queryClient.invalidateQueries({ queryKey: ["notifications"] });
    },
    onError: (err: unknown) => {
      setError(
        err instanceof ApiError ? err.message : "Delivery failed safely.",
      );
    },
  });
  const busy = approve.isPending || deliver.isPending;
  return (
    <tr>
      <td className="px-3 py-3">{item.template_key}</td>
      <td className="px-3 py-3">{item.source_event_type}</td>
      <td className="px-3 py-3">{item.source_resource_type}</td>
      <td className="px-3 py-3">{item.channel}</td>
      <td className="px-3 py-3">{item.destination_reference ?? "—"}</td>
      <td className="px-3 py-3">{item.provider_key ?? "pending"}</td>
      <td className="px-3 py-3">{item.provider_message_id ?? "—"}</td>
      <td className="px-3 py-3">
        <StatusBadge status={item.status} />
      </td>
      <td className="px-3 py-3">{item.attempt_count}</td>
      <td className="px-3 py-3">
        {new Date(item.created_at).toLocaleString()}
      </td>
      <td className="px-3 py-3">
        {mayApprove && item.status === "pending_approval" && (
          <button
            className="button-primary"
            disabled={busy}
            onClick={() => approve.mutate()}
          >
            {approve.isPending ? "Approving…" : "Approve"}
          </button>
        )}
        {mayApprove && item.status === "approved" && (
          <button
            className="button-primary"
            disabled={busy}
            onClick={() => deliver.mutate()}
          >
            {deliver.isPending ? "Delivering…" : "Deliver"}
          </button>
        )}
        {item.status === "delivered" && (
          <span className="text-slate-400">Delivered</span>
        )}
        {item.status === "failed" && (
          <span className="text-red-300">
            Failed{item.failure_reason ? `: ${item.failure_reason}` : ""}
          </span>
        )}
        {error && (
          <p role="alert" className="mt-1 text-sm text-red-300">
            {error}
          </p>
        )}
      </td>
    </tr>
  );
}

export function NotificationsPage() {
  const organization = useAuth().me?.organizations[0];
  const [status, setStatus] = useState<NotificationStatus | "">("");
  const [page, setPage] = useState(1);
  const notifications = useQuery({
    queryKey: ["notifications", organization?.id, status, page],
    enabled: Boolean(organization),
    queryFn: () => {
      const params = new URLSearchParams({
        organization_id: organization!.id,
        page: String(page),
        page_size: "10",
      });
      if (status) params.set("status", status);
      return api<Page<NotificationEvent>>(`/api/v1/notifications?${params}`);
    },
  });
  if (!organization) return <p>No organization selected.</p>;
  const mayApprove = approveRoles.includes(organization.role);
  return (
    <section aria-labelledby="notifications-title">
      <div>
        <h1 id="notifications-title" className="text-3xl font-bold">
          Notifications
        </h1>
        <p className="mt-2 text-slate-400">
          Critical findings generate a pending-approval notification event.
          Nothing is delivered until an authorized user approves it, and
          ordinary tests use the deterministic mock provider. The local demo
          stack can route approved email through Mailpit.
        </p>
      </div>
      <div className="mt-8 flex flex-wrap gap-3">
        <label>
          Status
          <select
            className="input mt-1 block"
            value={status}
            onChange={(event) => {
              setStatus(event.target.value as NotificationStatus | "");
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
      {notifications.isLoading && (
        <p aria-live="polite">Loading notifications…</p>
      )}
      {notifications.isError && (
        <p role="alert">Unable to load notifications.</p>
      )}
      {notifications.data?.items.length === 0 && (
        <p className="mt-5">No notifications.</p>
      )}
      {Boolean(notifications.data?.items.length) && (
        <div className="mt-5 overflow-x-auto">
          <table className="w-full text-left">
            <thead>
              <tr>
                <th className="px-3 py-2">Template</th>
                <th className="px-3 py-2">Event type</th>
                <th className="px-3 py-2">Source</th>
                <th className="px-3 py-2">Channel</th>
                <th className="px-3 py-2">Recipient</th>
                <th className="px-3 py-2">Provider</th>
                <th className="px-3 py-2">Provider message</th>
                <th className="px-3 py-2">Status</th>
                <th className="px-3 py-2">Attempts</th>
                <th className="px-3 py-2">Created</th>
                <th className="px-3 py-2">Action</th>
              </tr>
            </thead>
            <tbody>
              {notifications.data?.items.map((item) => (
                <NotificationRow
                  key={item.id}
                  item={item}
                  organizationId={organization.id}
                  mayApprove={mayApprove}
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
          disabled={page * 10 >= (notifications.data?.total ?? 0)}
          onClick={() => setPage((value) => value + 1)}
        >
          Next
        </button>
      </div>
    </section>
  );
}
