import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { aiQueryKeys } from "../ai/queryKeys";
import { ApiError, api } from "../api/client";
import type { AIRequestRecord, AITaskType, Organization, Page } from "../types";

const labels: Record<AITaskType, string> = {
  explain_finding: "Explain finding",
  explain_business_impact: "Explain business impact",
  suggest_remediation: "Generate remediation draft",
  executive_summary: "Generate executive summary",
  jira_description: "Generate Jira draft",
  email_summary: "Generate email draft",
};
const generationRoles = [
  "owner",
  "admin",
  "security_analyst",
  "cloud_engineer",
];
const safeErrors: Record<string, string> = {
  AI_IDEMPOTENCY_CONFLICT: "Use a new request key for changed evidence.",
  AI_RATE_LIMITED:
    "AI generation is rate limited. Try again after the quota resets.",
  AI_PROVIDER_DISABLED: "AI generation is disabled.",
  AI_PROVIDER_TIMEOUT: "AI generation timed out.",
  AI_PROVIDER_FAILED: "The AI provider is unavailable.",
  AI_INVALID_RESPONSE: "An invalid provider response was rejected.",
  AI_UNSUPPORTED_SOURCE_TASK:
    "This action is not supported for the selected source.",
  AI_SOURCE_NOT_FOUND: "The source is unavailable.",
};

export function AIWorkflow({
  organization,
  sourceType,
  sourceId,
  tasks,
}: {
  organization: Organization;
  sourceType: "finding" | "risk_assessment" | "compliance_assessment";
  sourceId: string;
  tasks: AITaskType[];
}) {
  const client = useQueryClient();
  const [announcement, setAnnouncement] = useState("");
  const scope = `${organization.id}:${sourceType}:${sourceId}`;
  const [latest, setLatest] = useState<{
    scope: string;
    record: AIRequestRecord;
  } | null>(null);
  const [selectedTask, setSelectedTask] = useState<AITaskType | null>(null);
  const confirmRef = useRef<HTMLButtonElement>(null);
  const cancelRef = useRef<HTMLButtonElement>(null);
  const triggerRef = useRef<HTMLButtonElement | null>(null);
  const historyKey = aiQueryKeys.history(organization.id, {
    sourceType,
    sourceId,
    pageSize: 10,
  });
  const history = useQuery({
    queryKey: historyKey,
    queryFn: () =>
      api<Page<AIRequestRecord>>(
        `/api/v1/ai/requests?organization_id=${organization.id}` +
          `&source_type=${sourceType}&source_id=${sourceId}&page_size=10`,
      ),
  });
  const generation = useMutation({
    mutationFn: (task: AITaskType) =>
      api<AIRequestRecord>("/api/v1/ai/generate", {
        method: "POST",
        body: JSON.stringify({
          organization_id: organization.id,
          task_type: task,
          sources: [{ source_type: sourceType, source_id: sourceId }],
          idempotency_key: `${task}:${sourceId}:${crypto.randomUUID()}`,
        }),
      }),
    onSuccess: async (result) => {
      setLatest({ scope, record: result });
      setSelectedTask(null);
      setAnnouncement("AI-generated draft is ready. Human review is required.");
      queueMicrotask(() => triggerRef.current?.focus());
      await client.invalidateQueries({
        queryKey: historyKey,
      });
    },
  });
  const error =
    generation.error instanceof ApiError
      ? (safeErrors[generation.error.code ?? ""] ??
        "AI generation failed safely.")
      : "AI generation failed safely.";
  const visible =
    (latest?.scope === scope ? latest.record : null) ??
    (Array.isArray(history.data?.items) ? history.data.items[0] : undefined) ??
    null;
  const copyVisible = () => {
    if (!visible?.content || !navigator.clipboard?.writeText) {
      setAnnouncement("AI draft could not be copied.");
      return;
    }
    void navigator.clipboard
      .writeText(
        [
          visible.content.title,
          visible.content.summary,
          ...visible.content.details,
          ...visible.content.caveats,
        ].join("\n"),
      )
      .then(() => setAnnouncement("AI draft copied to clipboard."))
      .catch(() => setAnnouncement("AI draft could not be copied."));
  };
  useEffect(() => {
    if (!selectedTask) return;
    confirmRef.current?.focus();
    const close = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !generation.isPending) {
        setSelectedTask(null);
        queueMicrotask(() => triggerRef.current?.focus());
      }
      if (event.key === "Tab") {
        const first = confirmRef.current;
        const last = cancelRef.current;
        if (!first || !last) return;
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first.focus();
        }
      }
    };
    document.addEventListener("keydown", close);
    return () => document.removeEventListener("keydown", close);
  }, [generation.isPending, selectedTask]);
  return (
    <section className="card" aria-labelledby={`ai-actions-${sourceId}`}>
      <h2 id={`ai-actions-${sourceId}`} className="text-xl font-bold">
        AI explanation and draft actions
      </h2>
      <p className="mt-2 text-sm text-amber-200">
        AI output is non-authoritative, may be inaccurate, and requires human
        review.
      </p>
      <p className="sr-only" aria-live="polite">
        {generation.isPending ? "Generating AI draft." : announcement}
      </p>
      {generationRoles.includes(organization.role) && (
        <div className="mt-3 flex flex-wrap gap-2">
          {tasks.map((task) => (
            <button
              key={task}
              type="button"
              className="button-secondary"
              disabled={generation.isPending}
              onClick={(event) => {
                triggerRef.current = event.currentTarget;
                setSelectedTask(task);
              }}
            >
              {labels[task]}
            </button>
          ))}
        </div>
      )}
      {selectedTask && (
        <div
          className="fixed inset-0 z-50 grid place-items-center bg-slate-950/75 p-4"
          aria-hidden={false}
        >
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby={`ai-confirm-${sourceId}`}
            className="card max-w-lg"
          >
            <h3 id={`ai-confirm-${sourceId}`} className="text-xl font-bold">
              Confirm AI draft generation
            </h3>
            <p className="mt-3">
              Generate “{labels[selectedTask]}” from the current persisted
              evidence? The result is advisory and requires human review.
            </p>
            <div className="mt-5 flex gap-3">
              <button
                ref={confirmRef}
                type="button"
                className="button-primary"
                disabled={generation.isPending}
                onClick={() => generation.mutate(selectedTask)}
              >
                {generation.isPending ? "Generating…" : "Generate AI draft"}
              </button>
              <button
                ref={cancelRef}
                type="button"
                className="button-secondary"
                disabled={generation.isPending}
                onClick={() => {
                  setSelectedTask(null);
                  queueMicrotask(() => triggerRef.current?.focus());
                }}
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}
      {generation.isError && (
        <p role="alert" className="mt-3 text-red-300">
          {error}
        </p>
      )}
      {history.isLoading && <p className="mt-3">Loading previous AI drafts…</p>}
      {visible?.content && (
        <article className="mt-4 border-t border-slate-700 pt-4">
          <h3 className="font-bold">{visible.content.title}</h3>
          <p className="mt-2 whitespace-pre-wrap">{visible.content.summary}</p>
          <p className="mt-2 text-sm">
            Generated {new Date(visible.created_at).toLocaleString()} from{" "}
            {sourceType} {sourceId}; provider {visible.provider_key}/
            {visible.model_key}; prompt {visible.prompt_key} v
            {visible.prompt_version}.
          </p>
          <p className="mt-2 text-sm" role="status">
            Source version {visible.source_version}:{" "}
            {visible.source_staleness === "current"
              ? "current evidence"
              : visible.source_staleness === "stale"
                ? "stale — regenerate to use current evidence"
                : "source unavailable — historical draft retained"}
          </p>
          <button
            type="button"
            className="button-secondary mt-3"
            onClick={copyVisible}
          >
            Copy AI draft
          </button>
        </article>
      )}
    </section>
  );
}
