import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { aiQueryKeys } from "../ai/queryKeys";
import { AIWorkflow } from "../components/AIWorkflow";
import type { AIRequestRecord, Organization, Role } from "../types";

const organization = (id: string, role: Role = "owner"): Organization => ({
  id,
  name: `Organization ${id}`,
  slug: `organization-${id}`,
  role,
});

const record = (
  organizationId: string,
  sourceId: string,
  summary = `Draft for ${organizationId}`,
): AIRequestRecord => ({
  id: `request-${organizationId}`,
  organization_id: organizationId,
  requested_by_user_id: "user-1",
  task_type: "explain_finding",
  status: "completed",
  provider_key: "mock",
  model_key: "cloudops-deterministic-mock-v1",
  prompt_key: "CLOUDOPS_EXPLAIN_FINDING_V1",
  prompt_version: 1,
  context_hash: "a".repeat(64),
  request_fingerprint: "b".repeat(64),
  response_schema_version: 1,
  error_code: null,
  finished_at: "2026-07-24T00:00:00Z",
  created_at: "2026-07-24T00:00:00Z",
  updated_at: "2026-07-24T00:00:00Z",
  source_type: "finding",
  source_id: sourceId,
  source_version: 1,
  source_staleness: "current",
  content: {
    title: `Title ${organizationId}`,
    summary,
    details: ["Persisted evidence only."],
    caveats: ["Human review required."],
    source_references: [`finding:${sourceId}:v1`],
    draft_only: true,
  },
});

function renderWorkflow(
  org: Organization,
  sourceId = "finding-1",
  client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  }),
) {
  const view = render(
    <QueryClientProvider client={client}>
      <AIWorkflow
        organization={org}
        sourceType="finding"
        sourceId={sourceId}
        tasks={["explain_finding", "suggest_remediation"]}
      />
    </QueryClientProvider>,
  );
  return { ...view, client };
}

describe("Stage 7 AI workflow release contract", () => {
  it("scopes history, source, filter, and request keys by organization", () => {
    expect(
      aiQueryKeys.history("org-a", {
        sourceType: "finding",
        sourceId: "shared-id",
        taskType: "explain_finding",
        page: 2,
      }),
    ).not.toEqual(
      aiQueryKeys.history("org-b", {
        sourceType: "finding",
        sourceId: "shared-id",
        taskType: "explain_finding",
        page: 2,
      }),
    );
    expect(aiQueryKeys.request("org-a", "request-1")).not.toEqual(
      aiQueryKeys.request("org-b", "request-1"),
    );
    expect(aiQueryKeys.history("org-a", { page: 1 })).not.toEqual(
      aiQueryKeys.history("org-a", { page: 2 }),
    );
  });

  it("does not render a late result from the previous organization", async () => {
    let resolveA!: (response: Response) => void;
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("organization_id=org-a")) {
        return new Promise<Response>((resolve) => {
          resolveA = resolve;
        });
      }
      return Promise.resolve(
        new Response(
          JSON.stringify({
            items: [record("org-b", "finding-1")],
            total: 1,
            page: 1,
            page_size: 10,
          }),
          { status: 200 },
        ),
      );
    });
    vi.stubGlobal("fetch", fetchMock);
    const { rerender, client } = renderWorkflow(organization("org-a"));
    rerender(
      <QueryClientProvider client={client}>
        <AIWorkflow
          organization={organization("org-b")}
          sourceType="finding"
          sourceId="finding-1"
          tasks={["explain_finding"]}
        />
      </QueryClientProvider>,
    );
    expect(await screen.findByText("Draft for org-b")).toBeVisible();
    await act(async () => {
      resolveA(
        new Response(
          JSON.stringify({
            items: [record("org-a", "finding-1")],
            total: 1,
            page: 1,
            page_size: 10,
          }),
          { status: 200 },
        ),
      );
    });
    expect(screen.queryByText("Draft for org-a")).not.toBeInTheDocument();
  });

  it("provides modal focus containment, escape, cancel, and focus return", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async () =>
          new Response(
            JSON.stringify({ items: [], total: 0, page: 1, page_size: 10 }),
            { status: 200 },
          ),
      ),
    );
    renderWorkflow(organization("org-a"));
    const trigger = screen.getByRole("button", { name: "Explain finding" });
    await userEvent.click(trigger);
    const dialog = screen.getByRole("dialog", {
      name: "Confirm AI draft generation",
    });
    const confirm = screen.getByRole("button", {
      name: "Generate AI draft",
    });
    const cancel = screen.getByRole("button", { name: "Cancel" });
    expect(dialog).toHaveAttribute("aria-modal", "true");
    expect(confirm).toHaveFocus();
    await userEvent.tab({ shift: true });
    expect(cancel).toHaveFocus();
    await userEvent.tab();
    expect(confirm).toHaveFocus();
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
    await userEvent.click(trigger);
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(trigger).toHaveFocus();
  });

  it.each([
    ["AI_IDEMPOTENCY_CONFLICT", "Use a new request key"],
    ["AI_RATE_LIMITED", "rate limited"],
    ["AI_PROVIDER_DISABLED", "generation is disabled"],
    ["AI_PROVIDER_TIMEOUT", "generation timed out"],
    ["AI_PROVIDER_FAILED", "provider is unavailable"],
    ["AI_INVALID_RESPONSE", "invalid provider response"],
    ["AI_UNSUPPORTED_SOURCE_TASK", "action is not supported"],
    ["AI_SOURCE_NOT_FOUND", "source is unavailable"],
  ])("renders a safe distinct state for %s", async (code, message) => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) =>
        init?.method === "POST"
          ? new Response(
              JSON.stringify({ error: { code, message: "unsafe internal" } }),
              { status: 409 },
            )
          : new Response(
              JSON.stringify({ items: [], total: 0, page: 1, page_size: 10 }),
              { status: 200 },
            ),
      ),
    );
    renderWorkflow(organization("org-a"));
    await userEvent.click(
      screen.getByRole("button", { name: "Explain finding" }),
    );
    await userEvent.click(
      screen.getByRole("button", { name: "Generate AI draft" }),
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(message);
    expect(screen.getByRole("alert")).not.toHaveTextContent("unsafe internal");
  });

  it.each([
    ["success", true, "AI draft copied to clipboard."],
    ["rejection", false, "AI draft could not be copied."],
  ])(
    "announces clipboard %s and keeps copy usable",
    async (_case, succeeds, text) => {
      vi.stubGlobal(
        "fetch",
        vi.fn(
          async () =>
            new Response(
              JSON.stringify({
                items: [record("org-a", "finding-1", "<img onerror=alert(1)>")],
                total: 1,
                page: 1,
                page_size: 10,
              }),
              { status: 200 },
            ),
        ),
      );
      const writeText = succeeds
        ? vi.fn(async () => undefined)
        : vi.fn(async () => {
            throw new Error("denied");
          });
      Object.defineProperty(navigator, "clipboard", {
        configurable: true,
        value: { writeText },
      });
      renderWorkflow(organization("org-a"));
      expect(
        await screen.findByText("<img onerror=alert(1)>"),
      ).toBeInTheDocument();
      expect(document.querySelector("img")).toBeNull();
      const copy = screen.getByRole("button", { name: "Copy AI draft" });
      await userEvent.click(copy);
      expect(await screen.findByText(text)).toBeInTheDocument();
      expect(copy).toBeEnabled();
    },
  );

  it("hides generation from read-only roles while retaining authorized history", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async () =>
          new Response(
            JSON.stringify({
              items: [record("org-a", "finding-1")],
              total: 1,
              page: 1,
              page_size: 10,
            }),
            { status: 200 },
          ),
      ),
    );
    renderWorkflow(organization("org-a", "auditor"));
    expect(await screen.findByText("Draft for org-a")).toBeVisible();
    expect(
      screen.queryByRole("button", { name: "Explain finding" }),
    ).not.toBeInTheDocument();
  });
});
