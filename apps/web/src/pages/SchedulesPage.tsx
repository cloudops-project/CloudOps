import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, ApiError } from "../api/client";
import { useAuth } from "../auth/AuthProvider";
import type { AWSAccount, Page, ScanRun, ScanSchedule } from "../types";

const manageRoles = ["owner", "admin", "security_analyst", "cloud_engineer"];

function ScheduleRow({
  item,
  organizationId,
  mayManage,
}: {
  item: ScanSchedule;
  organizationId: string;
  mayManage: boolean;
}) {
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);

  const invalidate = () =>
    Promise.all([
      queryClient.invalidateQueries({ queryKey: ["schedules"] }),
      queryClient.invalidateQueries({ queryKey: ["scan-runs"] }),
    ]);

  const toggle = useMutation({
    mutationFn: () =>
      api<ScanSchedule>(
        `/api/v1/schedules/${item.id}/${item.enabled ? "disable" : "enable"}?organization_id=${organizationId}`,
        { method: "POST" },
      ),
    onSuccess: async () => {
      setError(null);
      await invalidate();
    },
    onError: (err: unknown) =>
      setError(
        err instanceof ApiError ? err.message : "Unable to update schedule.",
      ),
  });
  const runNow = useMutation({
    mutationFn: () =>
      api<ScanRun>(
        `/api/v1/schedules/${item.id}/run?organization_id=${organizationId}`,
        { method: "POST" },
      ),
    onSuccess: async () => {
      setError(null);
      await invalidate();
    },
    onError: (err: unknown) =>
      setError(err instanceof ApiError ? err.message : "Unable to run scan."),
  });
  const remove = useMutation({
    mutationFn: () =>
      api<void>(
        `/api/v1/schedules/${item.id}?organization_id=${organizationId}`,
        {
          method: "DELETE",
        },
      ),
    onSuccess: async () => {
      setError(null);
      await invalidate();
    },
    onError: (err: unknown) =>
      setError(
        err instanceof ApiError ? err.message : "Unable to delete schedule.",
      ),
  });

  const busy = toggle.isPending || runNow.isPending || remove.isPending;

  return (
    <tr>
      <td className="px-3 py-3">{item.name}</td>
      <td className="px-3 py-3">Every {item.interval_minutes} min</td>
      <td className="px-3 py-3">{item.enabled ? "Enabled" : "Disabled"}</td>
      <td className="px-3 py-3">
        {item.last_run_at
          ? new Date(item.last_run_at).toLocaleString()
          : "Never"}
      </td>
      <td className="px-3 py-3">
        {item.enabled && item.next_run_at
          ? new Date(item.next_run_at).toLocaleString()
          : "—"}
      </td>
      <td className="px-3 py-3">
        {mayManage && (
          <div className="flex flex-wrap gap-2">
            <button
              className="button-secondary"
              disabled={busy}
              onClick={() => toggle.mutate()}
            >
              {item.enabled ? "Disable" : "Enable"}
            </button>
            {item.enabled && (
              <button
                className="button-primary"
                disabled={busy}
                onClick={() => runNow.mutate()}
              >
                {runNow.isPending ? "Running…" : "Run now"}
              </button>
            )}
            <button
              className="button-secondary"
              disabled={busy}
              onClick={() => remove.mutate()}
            >
              Delete
            </button>
          </div>
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

function CreateScheduleForm({
  organizationId,
  accounts,
}: {
  organizationId: string;
  accounts: AWSAccount[];
}) {
  const queryClient = useQueryClient();
  const [accountId, setAccountId] = useState("");
  const [name, setName] = useState("");
  const [intervalMinutes, setIntervalMinutes] = useState("60");
  const [error, setError] = useState<string | null>(null);

  const create = useMutation({
    mutationFn: () =>
      api<ScanSchedule>(`/api/v1/schedules?organization_id=${organizationId}`, {
        method: "POST",
        body: JSON.stringify({
          aws_account_id: accountId,
          name,
          interval_minutes: Number(intervalMinutes),
        }),
      }),
    onSuccess: async () => {
      setError(null);
      setName("");
      setIntervalMinutes("60");
      setAccountId("");
      await queryClient.invalidateQueries({ queryKey: ["schedules"] });
    },
    onError: (err: unknown) =>
      setError(
        err instanceof ApiError ? err.message : "Unable to create schedule.",
      ),
  });

  return (
    <div className="card my-5 grid gap-3 md:grid-cols-4">
      <label>
        <span className="label">AWS account</span>
        <select
          className="input"
          value={accountId}
          onChange={(event) => setAccountId(event.target.value)}
        >
          <option value="">Select an account</option>
          {accounts.map((account) => (
            <option key={account.id} value={account.id}>
              {account.name}
            </option>
          ))}
        </select>
      </label>
      <label>
        <span className="label">Schedule name</span>
        <input
          className="input"
          value={name}
          onChange={(event) => setName(event.target.value)}
        />
      </label>
      <label>
        <span className="label">Interval (minutes, min 15)</span>
        <input
          className="input"
          type="number"
          min={15}
          value={intervalMinutes}
          onChange={(event) => setIntervalMinutes(event.target.value)}
        />
      </label>
      <div className="flex items-end">
        <button
          className="button"
          disabled={
            !accountId ||
            name.trim().length === 0 ||
            Number(intervalMinutes) < 15 ||
            create.isPending
          }
          onClick={() => create.mutate()}
        >
          {create.isPending ? "Creating…" : "Create schedule"}
        </button>
      </div>
      {error && (
        <p role="alert" className="text-sm text-red-300 md:col-span-4">
          {error}
        </p>
      )}
    </div>
  );
}

export function SchedulesPage() {
  const organization = useAuth().me?.organizations[0];
  const [page, setPage] = useState(1);
  const mayManage = Boolean(
    organization && manageRoles.includes(organization.role),
  );

  const accounts = useQuery({
    queryKey: ["aws-accounts", organization?.id],
    enabled: Boolean(organization) && mayManage,
    queryFn: () =>
      api<AWSAccount[]>(
        `/api/v1/aws/accounts?organization_id=${organization!.id}`,
      ),
  });
  const schedules = useQuery({
    queryKey: ["schedules", organization?.id, page],
    enabled: Boolean(organization),
    queryFn: () =>
      api<Page<ScanSchedule>>(
        `/api/v1/schedules?organization_id=${organization!.id}&page=${page}&page_size=10`,
      ),
  });
  const runs = useQuery({
    queryKey: ["scan-runs", organization?.id],
    enabled: Boolean(organization),
    queryFn: () =>
      api<Page<ScanRun>>(
        `/api/v1/scan-runs?organization_id=${organization!.id}&page=1&page_size=10`,
      ),
    // "Run now" only enqueues a job; a worker processes it moments later. Without
    // polling, the run would stay visibly PENDING after a single invalidation.
    // Poll only while a run is actually active, then stop.
    refetchInterval: (query) =>
      query.state.data?.items.some(
        (run) => run.status === "pending" || run.status === "running",
      )
        ? 2000
        : false,
  });

  if (!organization) return <p>No organization selected.</p>;

  return (
    <section aria-labelledby="schedules-title">
      <div>
        <h1 id="schedules-title" className="text-3xl font-bold">
          Scheduled scans
        </h1>
        <p className="mt-2 text-slate-400">
          Each schedule runs the existing discovery and evaluation pipeline on a
          cadence. No new AWS calls or mutation logic exist here — a scheduled
          run behaves exactly like clicking "Run evaluation" manually.
        </p>
      </div>
      {mayManage && (
        <CreateScheduleForm
          organizationId={organization.id}
          accounts={accounts.data ?? []}
        />
      )}
      {schedules.isLoading && <p aria-live="polite">Loading schedules…</p>}
      {schedules.isError && <p role="alert">Unable to load schedules.</p>}
      {schedules.data?.items.length === 0 && (
        <p className="mt-5">No schedules yet.</p>
      )}
      {Boolean(schedules.data?.items.length) && (
        <div className="mt-5 overflow-x-auto">
          <table className="w-full text-left">
            <thead>
              <tr>
                <th className="px-3 py-2">Name</th>
                <th className="px-3 py-2">Cadence</th>
                <th className="px-3 py-2">Status</th>
                <th className="px-3 py-2">Last run</th>
                <th className="px-3 py-2">Next run</th>
                <th className="px-3 py-2">Action</th>
              </tr>
            </thead>
            <tbody>
              {schedules.data?.items.map((item) => (
                <ScheduleRow
                  key={item.id}
                  item={item}
                  organizationId={organization.id}
                  mayManage={mayManage}
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
          disabled={page * 10 >= (schedules.data?.total ?? 0)}
          onClick={() => setPage((value) => value + 1)}
        >
          Next
        </button>
      </div>

      <h2 className="mt-10 text-xl font-bold">Recent scan runs</h2>
      {runs.isLoading && <p aria-live="polite">Loading scan runs…</p>}
      {runs.isError && <p role="alert">Unable to load scan runs.</p>}
      {runs.data?.items.length === 0 && (
        <p className="mt-3">No scan runs yet.</p>
      )}
      {Boolean(runs.data?.items.length) && (
        <div className="mt-3 overflow-x-auto">
          <table className="w-full text-left">
            <thead>
              <tr>
                <th className="px-3 py-2">Trigger</th>
                <th className="px-3 py-2">Status</th>
                <th className="px-3 py-2">Started</th>
                <th className="px-3 py-2">Finished</th>
                <th className="px-3 py-2">Detail</th>
              </tr>
            </thead>
            <tbody>
              {runs.data?.items.map((run) => (
                <tr key={run.id}>
                  <td className="px-3 py-3 capitalize">{run.trigger}</td>
                  <td className="px-3 py-3 capitalize">{run.status}</td>
                  <td className="px-3 py-3">
                    {run.started_at
                      ? new Date(run.started_at).toLocaleString()
                      : "—"}
                  </td>
                  <td className="px-3 py-3">
                    {run.finished_at
                      ? new Date(run.finished_at).toLocaleString()
                      : "—"}
                  </td>
                  <td className="px-3 py-3">
                    {run.status === "failed" ? (
                      <span className="text-red-300">
                        {run.error_summary ?? "Failed"}
                      </span>
                    ) : (
                      "—"
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
