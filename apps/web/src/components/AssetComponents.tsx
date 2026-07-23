import type { Asset, DiscoveryStatus } from "../types";

const jobStyles: Record<DiscoveryStatus, string> = {
  pending: "bg-amber-500/15 text-amber-300",
  running: "bg-blue-500/15 text-blue-300",
  completed: "bg-green-500/15 text-green-300",
  partially_completed: "bg-amber-500/15 text-amber-300",
  failed: "bg-red-500/15 text-red-300",
};

export function DiscoveryStatusBadge({ status }: { status: DiscoveryStatus }) {
  return (
    <span
      className={`rounded-full px-3 py-1 text-xs font-bold uppercase ${jobStyles[status]}`}
    >
      {status.replace("_", " ")}
    </span>
  );
}

export function AssetLifecycleBadge({ active }: { active: boolean }) {
  return (
    <span
      className={`rounded-full px-3 py-1 text-xs font-bold uppercase ${
        active
          ? "bg-green-500/15 text-green-300"
          : "bg-slate-500/20 text-slate-300"
      }`}
    >
      {active ? "Active" : "Stale"}
    </span>
  );
}

export function AssetJson({ asset }: { asset: Asset }) {
  return (
    <div className="grid gap-5 lg:grid-cols-2">
      <section className="card">
        <h2 className="text-xl font-bold">Tags</h2>
        <pre className="mt-4 overflow-auto rounded-button bg-slate-950 p-4 text-xs">
          {JSON.stringify(asset.tags, null, 2)}
        </pre>
      </section>
      <section className="card">
        <h2 className="text-xl font-bold">Service metadata</h2>
        <pre className="mt-4 overflow-auto rounded-button bg-slate-950 p-4 text-xs">
          {JSON.stringify(asset.metadata, null, 2)}
        </pre>
      </section>
    </div>
  );
}
