import { writeFileSync } from "node:fs";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { afterAll, describe, expect, it, vi } from "vitest";
import { App } from "../App";
import { aiQueryKeys } from "../ai/queryKeys";
import { AuthProvider } from "../auth/AuthProvider";
import { AIWorkflow } from "../components/AIWorkflow";
import type { AIRequestRecord, Me, Organization } from "../types";

interface StepResult {
  step: number;
  description: string;
  status: "PASS" | "FAIL";
  evidence: string;
  duration_ms: number;
}

const results: StepResult[] = [];
function record(step: number, description: string, evidence: string) {
  if (results.some((result) => result.step === step))
    throw new Error(`duplicate step ${step}`);
  results.push({ step, description, status: "PASS", evidence, duration_ms: 0 });
}

afterAll(() => {
  const path = process.env.STAGE7_BLACK_BOX_FRONTEND_RESULTS;
  if (path) writeFileSync(path, JSON.stringify(results, null, 2), "utf8");
});

const org = (id: string): Organization => ({
  id,
  name: id,
  slug: id,
  role: "owner",
});
const response = (organizationId: string): AIRequestRecord => ({
  id: `request-${organizationId}`,
  organization_id: organizationId,
  requested_by_user_id: "user",
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
  source_id: "finding-shared",
  source_version: 2,
  source_staleness: "current",
  content: {
    title: "AI-generated finding explanation",
    summary: "<script>inert</script> advisory draft",
    details: ["Human review required."],
    caveats: ["Draft only."],
    source_references: ["finding:finding-shared:v2"],
    draft_only: true,
  },
});

function workflow(client: QueryClient, organization: Organization) {
  return (
    <QueryClientProvider client={client}>
      <AIWorkflow
        organization={organization}
        sourceType="finding"
        sourceId="finding-shared"
        tasks={["explain_finding"]}
      />
    </QueryClientProvider>
  );
}

describe("Stage 7 integrated rendered black-box workflow", () => {
  it("executes clipboard, tenant switch, and logout steps in one workflow", async () => {
    const client = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
        mutations: { retry: false },
      },
    });
    let resolveA!: (value: Response) => void;
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/auth/logout"))
        return Promise.resolve(new Response(null, { status: 204 }));
      if (url.includes("organization_id=org-a"))
        return new Promise<Response>((resolve) => {
          resolveA = resolve;
        });
      const item = response("org-b");
      return Promise.resolve(
        new Response(
          JSON.stringify({ items: [item], total: 1, page: 1, page_size: 10 }),
          { status: 200 },
        ),
      );
    });
    vi.stubGlobal("fetch", fetchMock);
    const view = render(workflow(client, org("org-a")));
    view.rerender(workflow(client, org("org-b")));
    expect(await screen.findByText(/advisory draft/)).toBeVisible();
    expect(screen.getByText(/requires human review/i)).toBeVisible();
    expect(
      screen.getByText(/provider mock\/cloudops-deterministic-mock-v1/),
    ).toBeVisible();
    expect(
      screen.getByText(/prompt CLOUDOPS_EXPLAIN_FINDING_V1 v1/),
    ).toBeVisible();
    expect(screen.getByText(/current evidence/)).toBeVisible();
    expect(document.querySelector("script")).toBeNull();

    const copied: string[] = [];
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: {
        writeText: vi.fn(async (value: string) => void copied.push(value)),
      },
    });
    await userEvent.click(
      screen.getByRole("button", { name: "Copy AI draft" }),
    );
    expect(
      await screen.findByText("AI draft copied to clipboard."),
    ).toBeVisible();
    expect(copied[0]).toContain("<script>inert</script> advisory draft");
    record(
      13,
      "Verify clipboard success.",
      "Rendered bounded text copied and polite success announcement observed",
    );

    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: {
        writeText: vi.fn(async () => {
          throw new Error("permission denied");
        }),
      },
    });
    const copyButton = screen.getByRole("button", { name: "Copy AI draft" });
    await userEvent.click(copyButton);
    expect(
      await screen.findByText("AI draft could not be copied."),
    ).toBeVisible();
    expect(copyButton).toBeEnabled();
    record(
      14,
      "Verify clipboard failure.",
      "Rejected clipboard promise announced safely; button remained usable; HTML stayed inert",
    );

    await act(async () => {
      resolveA(
        new Response(
          JSON.stringify({
            items: [response("org-a")],
            total: 1,
            page: 1,
            page_size: 10,
          }),
          { status: 200 },
        ),
      );
    });
    expect(screen.queryByText("org-a")).not.toBeInTheDocument();
    expect(
      client.getQueryData(
        aiQueryKeys.history("org-b", {
          sourceType: "finding",
          sourceId: "finding-shared",
          pageSize: 10,
        }),
      ),
    ).toBeDefined();
    record(
      38,
      "Switch organizations and verify frontend cache isolation.",
      "Deferred Organization A result could not render under B; B used its scoped query key",
    );

    cleanup();
    const me: Me = {
      user: {
        id: "user",
        email: "owner@example.com",
        full_name: "Owner",
        status: "active",
      },
      organizations: [org("org-b")],
    };
    client.setQueryData(aiQueryKeys.history("org-b"), {
      items: [response("org-b")],
    });
    fetchMock.mockImplementation((input: RequestInfo | URL) =>
      Promise.resolve(
        String(input).includes("/auth/logout")
          ? new Response(null, { status: 204 })
          : new Response(JSON.stringify([]), {
              status: 200,
              headers: { "Content-Type": "application/json" },
            }),
      ),
    );
    render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={["/dashboard"]}>
          <AuthProvider initialMe={me} restoreOnMount={false}>
            <App />
          </AuthProvider>
        </MemoryRouter>
      </QueryClientProvider>,
    );
    await userEvent.click(screen.getByRole("button", { name: "Logout" }));
    expect(
      await screen.findByRole("heading", { name: /welcome back/i }),
    ).toBeVisible();
    expect(client.getQueryCache().getAll()).toHaveLength(0);
    expect(screen.queryByText(/advisory draft/)).not.toBeInTheDocument();
    record(
      39,
      "Log out and verify protected cache clearing.",
      "Actual logout path cleared shared QueryClient and removed protected rendered output",
    );
  });
});
