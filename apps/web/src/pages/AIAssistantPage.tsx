import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../api/client";
import { useAuth } from "../auth/AuthProvider";
import type { AIRequestRecord, AITaskType, Page } from "../types";

const generationRoles = [
  "owner",
  "admin",
  "security_analyst",
  "cloud_engineer",
];
const tasks: Array<{ value: AITaskType; label: string }> = [
  { value: "explain_finding", label: "Explain finding" },
  { value: "explain_business_impact", label: "Explain business impact" },
  { value: "suggest_remediation", label: "Suggest remediation" },
  { value: "executive_summary", label: "Draft executive summary" },
  { value: "jira_description", label: "Draft Jira description" },
  { value: "email_summary", label: "Draft email summary" },
];

export function AIAssistantPage() {
  const organization = useAuth().me?.organizations[0];
  const [sourceId, setSourceId] = useState("");
  const [task, setTask] = useState<AITaskType>("explain_finding");
  const queryClient = useQueryClient();
  const history = useQuery({
    queryKey: ["ai-requests", organization?.id],
    enabled: Boolean(organization),
    queryFn: () =>
      api<Page<AIRequestRecord>>(
        `/api/v1/ai/requests?organization_id=${organization!.id}&page_size=25`,
      ),
  });
  const generation = useMutation({
    mutationFn: () =>
      api<AIRequestRecord>("/api/v1/ai/generate", {
        method: "POST",
        body: JSON.stringify({
          organization_id: organization!.id,
          task_type: task,
          sources: [
            {
              source_type:
                task === "executive_summary" ? "risk_assessment" : "finding",
              source_id: sourceId,
            },
          ],
          idempotency_key: `${task}:${sourceId}:${crypto.randomUUID()}`,
        }),
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["ai-requests"] });
    },
  });
  if (!organization) return <p>No organization selected.</p>;
  const mayGenerate = generationRoles.includes(organization.role);
  return (
    <section aria-labelledby="ai-title">
      <h1 id="ai-title" className="text-3xl font-bold">
        AI explanation assistant
      </h1>
      <p className="mt-2 max-w-3xl text-slate-300">
        Produce reviewable drafts from persisted CloudOps evidence. AI never
        detects findings, calculates risk, changes compliance, or executes
        remediation.
      </p>
      <div className="mt-6 rounded-lg border border-amber-700 bg-amber-950/30 p-4">
        <strong>Human review required.</strong> Outputs may be incomplete or
        inaccurate and are never sent or executed automatically.
      </div>
      {mayGenerate && (
        <form
          className="card mt-6 grid gap-4"
          onSubmit={(event) => {
            event.preventDefault();
            generation.mutate();
          }}
        >
          <label>
            <span className="mb-1 block">Task</span>
            <select
              value={task}
              onChange={(event) => setTask(event.target.value as AITaskType)}
            >
              {tasks.map((item) => (
                <option key={item.value} value={item.value}>
                  {item.label}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span className="mb-1 block">
              {task === "executive_summary"
                ? "Risk assessment ID"
                : "Finding ID"}
            </span>
            <input
              required
              value={sourceId}
              onChange={(event) => setSourceId(event.target.value)}
              placeholder="UUID"
            />
          </label>
          {generation.isError && (
            <p role="alert" className="text-red-300">
              The draft could not be generated safely.
            </p>
          )}
          <button
            className="button-primary justify-self-start"
            disabled={generation.isPending}
          >
            {generation.isPending ? "Generating…" : "Generate draft"}
          </button>
        </form>
      )}
      <h2 className="mt-8 text-2xl font-bold">Request history</h2>
      {history.isLoading && <p className="mt-3">Loading requests…</p>}
      {history.isError && (
        <p role="alert" className="mt-3 text-red-300">
          Request history is unavailable.
        </p>
      )}
      {history.data?.items.length === 0 && (
        <p className="mt-3">No AI drafts have been requested.</p>
      )}
      <div className="mt-4 grid gap-4">
        {history.data?.items.map((item) => (
          <article key={item.id} className="card">
            <div className="flex flex-wrap justify-between gap-2">
              <h3 className="font-bold">
                {item.content?.title ?? item.task_type.replaceAll("_", " ")}
              </h3>
              <span>{item.status}</span>
            </div>
            {item.content && (
              <>
                <p className="mt-3 whitespace-pre-wrap">
                  {item.content.summary}
                </p>
                <ul className="mt-3 list-disc pl-6">
                  {item.content.details.map((detail) => (
                    <li key={detail}>{detail}</li>
                  ))}
                </ul>
                <p className="mt-3 text-sm text-amber-200">
                  Draft only — validate against source evidence.
                </p>
              </>
            )}
          </article>
        ))}
      </div>
    </section>
  );
}
