import type {
  EvaluationStatus,
  FindingSeverity,
  FindingStatus,
} from "../types";

const severityStyles: Record<FindingSeverity, string> = {
  critical: "bg-red-950 text-red-200 border-red-700",
  high: "bg-orange-950 text-orange-200 border-orange-700",
  medium: "bg-yellow-950 text-yellow-100 border-yellow-700",
  low: "bg-green-950 text-green-200 border-green-700",
  informational: "bg-blue-950 text-blue-200 border-blue-700",
};

export function SeverityBadge({ severity }: { severity: FindingSeverity }) {
  return (
    <span
      className={`inline-flex rounded-full border px-3 py-1 text-xs font-semibold ${severityStyles[severity]}`}
    >
      Severity: {severity}
    </span>
  );
}

export function FindingStatusBadge({ status }: { status: FindingStatus }) {
  return (
    <span className="inline-flex rounded-full border border-slate-600 bg-slate-800 px-3 py-1 text-xs font-semibold">
      Status: {status}
    </span>
  );
}

export function EvaluationStatusBadge({
  status,
}: {
  status: EvaluationStatus;
}) {
  return (
    <span className="inline-flex rounded-full border border-blue-700 bg-blue-950 px-3 py-1 text-xs font-semibold text-blue-200">
      Evaluation: {status.replaceAll("_", " ")}
    </span>
  );
}

export function SafeEvidence({ value }: { value: Record<string, unknown> }) {
  return (
    <pre className="max-h-96 overflow-auto whitespace-pre-wrap break-all rounded-button bg-slate-950 p-4 text-xs text-slate-200">
      {JSON.stringify(value, null, 2)}
    </pre>
  );
}
