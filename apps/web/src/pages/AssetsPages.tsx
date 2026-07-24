import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Play, Search } from "lucide-react";
import type { ReactNode } from "react";
import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useParams } from "react-router";
import { api } from "../api/client";
import { useAuth } from "../auth/AuthProvider";
import {
  AssetJson,
  AssetLifecycleBadge,
  DiscoveryStatusBadge,
} from "../components/AssetComponents";
import type {
  AWSAccount,
  Asset,
  AssetType,
  DiscoveryJob,
  Page,
} from "../types";

const assetTypes: AssetType[] = [
  "ec2_instance",
  "s3_bucket",
  "iam_user",
  "iam_role",
  "iam_group",
  "iam_policy",
  "rds_instance",
];

function useOrganization() {
  return useAuth().me?.organizations[0];
}

export function AssetsPage() {
  const organization = useOrganization();
  const [page, setPage] = useState(1);
  const [filters, setFilters] = useState({
    aws_account_id: "",
    asset_type: "",
    region: "",
    status: "",
    is_active: "",
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
  const assets = useQuery({
    queryKey: ["assets", queryString],
    enabled: Boolean(organization),
    queryFn: () => api<Page<Asset>>(`/api/v1/assets?${queryString}`),
  });
  if (!organization) return <p>No organization selected.</p>;
  const updateFilter = (name: string, value: string) => {
    setPage(1);
    setFilters((current) => ({ ...current, [name]: value }));
  };
  return (
    <section>
      <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold">Asset inventory</h1>
          <p className="text-slate-400">
            Normalized AWS resources for {organization.name}
          </p>
        </div>
        <Link className="button-secondary" to="/discovery/jobs">
          Discovery jobs
        </Link>
      </div>
      <div className="card mb-5 grid gap-3 md:grid-cols-2 xl:grid-cols-6">
        <label className="xl:col-span-2">
          <span className="label">Search</span>
          <span className="relative block">
            <Search
              className="absolute left-3 top-3 text-slate-500"
              size={18}
            />
            <input
              aria-label="Search assets"
              className="input pl-10"
              value={filters.search}
              onChange={(event) => updateFilter("search", event.target.value)}
            />
          </span>
        </label>
        <Filter
          label="AWS account"
          value={filters.aws_account_id}
          onChange={(value) => updateFilter("aws_account_id", value)}
        >
          {accounts.data?.map((account) => (
            <option key={account.id} value={account.id}>
              {account.name}
            </option>
          ))}
        </Filter>
        <Filter
          label="Asset type"
          value={filters.asset_type}
          onChange={(value) => updateFilter("asset_type", value)}
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
            onChange={(event) => updateFilter("region", event.target.value)}
          />
        </label>
        <label>
          <span className="label">Status</span>
          <input
            className="input"
            value={filters.status}
            onChange={(event) => updateFilter("status", event.target.value)}
          />
        </label>
        <Filter
          label="Lifecycle"
          value={filters.is_active}
          onChange={(value) => updateFilter("is_active", value)}
        >
          <option value="true">Active</option>
          <option value="false">Stale</option>
        </Filter>
      </div>
      {assets.isLoading && <p aria-live="polite">Loading assets…</p>}
      {assets.isError && (
        <p role="alert" className="text-red-400">
          Unable to load assets.
        </p>
      )}
      {assets.data?.total === 0 && (
        <div className="card">No assets match these filters.</div>
      )}
      {assets.data && assets.data.total > 0 && (
        <div className="overflow-x-auto rounded-card border border-border">
          <table className="min-w-full bg-card text-left text-sm">
            <thead className="bg-slate-800 text-slate-300">
              <tr>
                {[
                  "Name",
                  "Type",
                  "AWS account",
                  "Region",
                  "Status",
                  "Lifecycle",
                  "Last seen",
                ].map((item) => (
                  <th className="p-4" key={item}>
                    {item}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {assets.data.items.map((item) => (
                <tr className="border-t border-border" key={item.id}>
                  <td className="p-4">
                    <Link className="text-blue-300" to={`/assets/${item.id}`}>
                      {item.name}
                    </Link>
                  </td>
                  <td className="p-4">{item.asset_type}</td>
                  <td className="p-4 font-mono text-xs">
                    {accounts.data?.find(
                      (account) => account.id === item.aws_account_id,
                    )?.name ?? item.aws_account_id}
                  </td>
                  <td className="p-4">{item.region}</td>
                  <td className="p-4">{item.status ?? "—"}</td>
                  <td className="p-4">
                    <AssetLifecycleBadge active={item.is_active} />
                  </td>
                  <td className="p-4">
                    {new Date(item.last_seen_at).toLocaleString()}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <div className="mt-5 flex items-center justify-between">
        <button
          className="button-secondary"
          disabled={page === 1}
          onClick={() => setPage((value) => value - 1)}
        >
          Previous
        </button>
        <span>Page {page}</span>
        <button
          className="button-secondary"
          disabled={
            !assets.data || page * assets.data.page_size >= assets.data.total
          }
          onClick={() => setPage((value) => value + 1)}
        >
          Next
        </button>
      </div>
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

export function AssetDetailsPage() {
  const organization = useOrganization();
  const { assetId } = useParams();
  const query = useQuery({
    queryKey: ["asset", assetId, organization?.id],
    enabled: Boolean(assetId && organization),
    queryFn: () =>
      api<Asset>(
        `/api/v1/assets/${assetId}?organization_id=${organization!.id}`,
      ),
  });
  if (query.isLoading) return <p>Loading asset…</p>;
  if (query.isError || !query.data)
    return (
      <p role="alert" className="text-red-400">
        Unable to load asset.
      </p>
    );
  const item = query.data;
  return (
    <section className="grid gap-5">
      <Link
        className="inline-flex items-center gap-2 text-blue-300"
        to="/assets"
      >
        <ArrowLeft size={18} />
        Assets
      </Link>
      <div className="card">
        <div className="flex justify-between gap-3">
          <div>
            <h1 className="text-3xl font-bold">{item.name}</h1>
            <p className="font-mono text-sm text-slate-400">
              {item.resource_id}
            </p>
          </div>
          <AssetLifecycleBadge active={item.is_active} />
        </div>
        <dl className="mt-6 grid gap-4 md:grid-cols-3">
          <Detail label="Type" value={item.asset_type} />
          <Detail label="Region" value={item.region} />
          <Detail label="Status" value={item.status ?? "—"} />
          <Detail
            label="First seen"
            value={new Date(item.first_seen_at).toLocaleString()}
          />
          <Detail
            label="Last seen"
            value={new Date(item.last_seen_at).toLocaleString()}
          />
          <Detail label="ARN" value={item.arn ?? "—"} />
        </dl>
      </div>
      <AssetJson asset={item} />
    </section>
  );
}

function Detail({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-sm text-slate-400">{label}</dt>
      <dd className="break-all">{value}</dd>
    </div>
  );
}

export function DiscoveryJobsPage() {
  const organization = useOrganization();
  const queryClient = useQueryClient();
  const accounts = useQuery({
    queryKey: ["aws-accounts", organization?.id],
    enabled: Boolean(organization),
    queryFn: () =>
      api<AWSAccount[]>(
        `/api/v1/aws/accounts?organization_id=${organization!.id}`,
      ),
  });
  const jobs = useQuery({
    queryKey: ["discovery-jobs", organization?.id],
    enabled: Boolean(organization),
    queryFn: () =>
      api<Page<DiscoveryJob>>(
        `/api/v1/discovery/jobs?organization_id=${organization!.id}`,
      ),
  });
  const [selected, setSelected] = useState("");
  const [confirmOpen, setConfirmOpen] = useState(false);
  const confirmButtonRef = useRef<HTMLButtonElement>(null);
  const cancelButtonRef = useRef<HTMLButtonElement>(null);
  const triggerButtonRef = useRef<HTMLButtonElement>(null);
  const canStart =
    organization &&
    ["owner", "admin", "security_analyst", "cloud_engineer"].includes(
      organization.role,
    );
  const start = useMutation({
    mutationFn: () =>
      api<DiscoveryJob>(`/api/v1/aws/accounts/${selected}/discover`, {
        method: "POST",
      }),
    onSuccess: () => {
      setConfirmOpen(false);
      setSelected("");
      void queryClient.invalidateQueries({ queryKey: ["discovery-jobs"] });
      queueMicrotask(() => triggerButtonRef.current?.focus());
    },
  });
  useEffect(() => {
    if (confirmOpen) confirmButtonRef.current?.focus();
  }, [confirmOpen]);
  const selectedAccount = accounts.data?.find((item) => item.id === selected);
  const closeConfirmation = () => {
    if (start.isPending) return;
    setConfirmOpen(false);
    queueMicrotask(() => triggerButtonRef.current?.focus());
  };
  if (!organization) return <p>No organization selected.</p>;
  return (
    <section>
      <h1 className="text-3xl font-bold">Discovery jobs</h1>
      <p className="text-slate-400">
        Inventory collection history for {organization.name}
      </p>
      {canStart && (
        <div className="card my-5 flex flex-wrap items-end gap-3">
          <Filter
            label="Connected account"
            value={selected}
            onChange={setSelected}
          >
            {accounts.data
              ?.filter((account) => account.connection_status === "connected")
              .map((account) => (
                <option key={account.id} value={account.id}>
                  {account.name}
                </option>
              ))}
          </Filter>
          <button
            ref={triggerButtonRef}
            className="button"
            disabled={!selected || start.isPending}
            onClick={() => setConfirmOpen(true)}
          >
            <Play size={18} />
            Run discovery
          </button>
        </div>
      )}
      {confirmOpen && selectedAccount && (
        <div className="fixed inset-0 z-50 grid place-items-center bg-slate-950/75 p-4">
          <div
            aria-labelledby="discovery-confirmation-title"
            aria-modal="true"
            className="card max-w-lg"
            onKeyDown={(event) => {
              if (event.key === "Escape") closeConfirmation();
              if (
                event.key === "Tab" &&
                !event.shiftKey &&
                document.activeElement === confirmButtonRef.current
              ) {
                event.preventDefault();
                cancelButtonRef.current?.focus();
              } else if (
                event.key === "Tab" &&
                event.shiftKey &&
                document.activeElement === cancelButtonRef.current
              ) {
                event.preventDefault();
                confirmButtonRef.current?.focus();
              }
            }}
            role="dialog"
          >
            <h2 id="discovery-confirmation-title" className="text-xl font-bold">
              Confirm inventory discovery
            </h2>
            <p className="mt-3 text-slate-300">
              CloudOps will read inventory metadata only from{" "}
              <strong>{selectedAccount.name}</strong> (
              <span>{selectedAccount.account_id}</span>). It will not change AWS
              resources or evaluate security posture.
            </p>
            <div className="mt-5 flex justify-end gap-3">
              <button
                ref={cancelButtonRef}
                className="button-secondary"
                disabled={start.isPending}
                onClick={closeConfirmation}
                type="button"
              >
                Cancel
              </button>
              <button
                ref={confirmButtonRef}
                className="button"
                disabled={start.isPending}
                onClick={() => {
                  if (!start.isPending) start.mutate();
                }}
                type="button"
              >
                {start.isPending ? "Starting…" : "Confirm discovery"}
              </button>
            </div>
          </div>
        </div>
      )}
      {start.isError && (
        <p role="alert" className="text-red-400">
          Unable to start discovery.
        </p>
      )}
      {jobs.isLoading && <p>Loading discovery jobs…</p>}
      {jobs.data?.total === 0 && (
        <div className="card mt-5">No discovery jobs have run.</div>
      )}
      <div className="mt-5 grid gap-4">
        {jobs.data?.items.map((job) => (
          <article className="card" key={job.id}>
            <div className="flex justify-between gap-3">
              <h2 className="font-bold">
                {accounts.data?.find((item) => item.id === job.aws_account_id)
                  ?.name ?? "AWS account"}
              </h2>
              <DiscoveryStatusBadge status={job.status} />
            </div>
            <div className="mt-4 grid grid-cols-2 gap-3 text-sm md:grid-cols-4">
              <span>Discovered: {job.assets_discovered}</span>
              <span>Created: {job.assets_created}</span>
              <span>Updated: {job.assets_updated}</span>
              <span>Deactivated: {job.assets_deactivated}</span>
            </div>
            {job.error_summary && (
              <p role="alert" className="mt-4 text-red-300">
                {job.error_summary}
              </p>
            )}
          </article>
        ))}
      </div>
    </section>
  );
}
