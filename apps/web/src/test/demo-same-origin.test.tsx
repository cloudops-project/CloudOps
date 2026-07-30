import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { describe, expect, it, vi } from "vitest";
import { App } from "../App";
import { AuthProvider } from "../auth/AuthProvider";
import type { Me, Page, RemediationRequest } from "../types";

/**
 * Demo regression tests.
 *
 * The demo serves the SPA and the API from one origin: the bundle is built with
 * an empty VITE_API_BASE_URL and Nginx proxies /api/ to the API container. These
 * tests pin the two browser-visible consequences of that design, plus the
 * dry-run badge that makes the safe remediation state visible.
 */

const owner: Me = {
  user: {
    id: "u1",
    email: "owner@cloudops-demo.testmail.com",
    full_name: "CloudOps Demo Owner",
    status: "active",
  },
  organizations: [
    { id: "o1", name: "CloudOps Demo", slug: "cloudops-demo", role: "owner" },
  ],
};

function dryRunRequest(
  overrides: Partial<RemediationRequest> = {},
): RemediationRequest {
  return {
    id: "r1",
    organization_id: "o1",
    aws_account_id: "a1",
    finding_id: "f1",
    rule_key: "EC2_SG_SSH_OPEN_TO_WORLD",
    rule_version: 1,
    requested_by_user_id: "u1",
    approved_by_user_id: null,
    rejected_by_user_id: null,
    status: "pending_approval",
    execution_mode: "mock_automation",
    automation_eligible: true,
    dry_run: true,
    title: "Remediate EC2_SG_SSH_OPEN_TO_WORLD",
    summary: "Restrict inbound SSH access.",
    remediation_steps_json: ["Restrict security group ingress"],
    verification_steps_json: ["Verify ingress no longer allows 0.0.0.0/0"],
    rollback_steps_json: ["Restore prior security group rules"],
    before_state_json: null,
    after_state_json: null,
    execution_result_json: null,
    attempt_count: 0,
    rejection_reason: null,
    failure_reason: null,
    requested_at: "2026-07-30T00:00:00Z",
    approved_at: null,
    rejected_at: null,
    cancelled_at: null,
    executed_at: null,
    failed_at: null,
    created_at: "2026-07-30T00:00:00Z",
    updated_at: "2026-07-30T00:00:00Z",
    ...overrides,
  };
}

function renderAt(path: string, me: Me, fetchImpl: typeof fetch) {
  vi.stubGlobal("fetch", fetchImpl);
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <AuthProvider initialMe={me} restoreOnMount={false}>
          <App />
        </AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("demo same-origin API access", () => {
  it("requests relative /api/v1 paths so one tunnel serves both origins", async () => {
    const seen: string[] = [];
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      seen.push(url);
      if (url.includes("/api/v1/remediations?")) {
        const body: Page<RemediationRequest> = {
          items: [dryRunRequest()],
          total: 1,
          page: 1,
          page_size: 10,
        };
        return new Response(JSON.stringify(body), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }
      return new Response(JSON.stringify([]), { status: 200 });
    });

    renderAt("/remediations", owner, fetchMock);
    expect(
      await screen.findByRole("heading", { name: "Remediation" }),
    ).toBeInTheDocument();

    const apiCalls = seen.filter((url) => url.includes("/api/v1/"));
    expect(apiCalls.length).toBeGreaterThan(0);
    for (const url of apiCalls) {
      // A same-origin call must not be absolute; an absolute URL means the
      // bundle was built with an external API base URL and would break behind a
      // temporary tunnel.
      expect(url.startsWith("/api/v1/")).toBe(true);
    }
  });

  it("shows the dry-run state so the safe workflow is visible", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/api/v1/remediations?")) {
        const body: Page<RemediationRequest> = {
          items: [dryRunRequest()],
          total: 1,
          page: 1,
          page_size: 10,
        };
        return new Response(JSON.stringify(body), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }
      return new Response(JSON.stringify([]), { status: 200 });
    });

    renderAt("/remediations", owner, fetchMock);
    expect(
      await screen.findByText("Remediate EC2_SG_SSH_OPEN_TO_WORLD"),
    ).toBeInTheDocument();

    const table = within(screen.getByRole("table"));
    expect(table.getByText("Dry run")).toBeInTheDocument();
    expect(table.getByText("mock automation")).toBeInTheDocument();
  });
});
