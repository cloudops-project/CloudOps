import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { describe, expect, it, vi } from "vitest";
import { App } from "../App";
import { AuthProvider } from "../auth/AuthProvider";
import type { DashboardSummary, Me, Role } from "../types";

function meFor(organizationId: string, role: Role = "owner"): Me {
  return {
    user: {
      id: "user-1",
      email: "owner@example.com",
      full_name: "Owner",
      status: "active",
    },
    organizations: [
      {
        id: organizationId,
        name: `Organization ${organizationId}`,
        slug: organizationId,
        role,
      },
    ],
  };
}

function emptySummary(organizationId: string): DashboardSummary {
  return {
    metadata: {
      organization_id: organizationId,
      generated_at: "2026-07-25T00:00:00Z",
      is_partial: true,
      missing_sections: [
        "accounts",
        "assets",
        "findings",
        "latest_completed_compliance_assessment",
        "latest_completed_risk_assessment",
        "latest_completed_discovery",
        "latest_completed_evaluation",
      ],
    },
    accounts: {
      total_accounts: 0,
      connected_accounts: 0,
      disconnected_accounts: 0,
      accounts_requiring_attention: 0,
    },
    assets: {
      total_assets: 0,
      active_assets: 0,
      inactive_assets: 0,
      counts_by_type: [],
      counts_by_region: [],
    },
    findings: {
      open_total: 0,
      resolved_total: 0,
      suppressed_total: 0,
      open_by_severity: [],
      open_by_service: [],
      open_by_account: [],
      recent_critical_and_high_findings: [],
    },
    compliance: {
      assessment_id: null,
      framework_key: null,
      framework_name: null,
      framework_version: null,
      assessment_status: null,
      evaluation_time: null,
      controls_total: 0,
      passed: 0,
      failed: 0,
      not_assessed: 0,
      error: 0,
      pass_percentage: null,
    },
    risk: {
      assessment_id: null,
      evaluation_time: null,
      aggregate_score: null,
      aggregate_priority: null,
      findings_total: 0,
      severity_counters: [],
      highest_risk_accounts: [],
      trend: [],
    },
    account_risk_heatmap: [],
    freshness: {
      latest_completed_discovery: null,
      latest_discovery: null,
      latest_completed_evaluation: null,
      latest_evaluation: null,
      latest_completed_compliance_assessment: null,
      latest_compliance_assessment: null,
      latest_completed_risk_assessment: null,
      latest_risk_assessment: null,
    },
  };
}

function populatedSummary(organizationId: string): DashboardSummary {
  return {
    ...emptySummary(organizationId),
    metadata: {
      organization_id: organizationId,
      generated_at: "2026-07-25T00:00:00Z",
      is_partial: false,
      missing_sections: [],
    },
    accounts: {
      total_accounts: 2,
      connected_accounts: 1,
      disconnected_accounts: 0,
      accounts_requiring_attention: 1,
    },
    assets: {
      total_assets: 2,
      active_assets: 1,
      inactive_assets: 1,
      counts_by_type: [{ key: "ec2_security_group", count: 1 }],
      counts_by_region: [{ key: "us-east-1", count: 1 }],
    },
    findings: {
      open_total: 3,
      resolved_total: 1,
      suppressed_total: 1,
      open_by_severity: [{ key: "critical", count: 1 }],
      open_by_service: [{ key: "network", count: 2 }],
      open_by_account: [],
      recent_critical_and_high_findings: [
        {
          id: "finding-1",
          aws_account_id: "account-1",
          asset_id: "asset-1",
          rule_key: "EC2_SG_SSH_OPEN_TO_WORLD",
          severity: "critical",
          status: "open",
          service: "network",
          region: "us-east-1",
          last_seen_at: "2026-07-25T13:00:00Z",
        },
      ],
    },
    compliance: {
      assessment_id: "assessment-1",
      framework_key: "cis",
      framework_name: "CIS Benchmark",
      framework_version: "1.0",
      assessment_status: "completed",
      evaluation_time: "2026-07-25T11:00:00Z",
      controls_total: 10,
      passed: 7,
      failed: 2,
      not_assessed: 1,
      error: 0,
      pass_percentage: 70,
    },
    risk: {
      assessment_id: "risk-1",
      evaluation_time: "2026-07-25T12:30:00Z",
      aggregate_score: 72,
      aggregate_priority: "high",
      findings_total: 5,
      severity_counters: [{ key: "critical", count: 1 }],
      highest_risk_accounts: [
        {
          aws_account_id: "account-1",
          account_display_identifier: "Account primary",
          score: 72,
          priority: "high",
          findings_total: 5,
          critical_count: 1,
          high_count: 1,
        },
      ],
      trend: [
        {
          assessment_id: "risk-0",
          evaluation_time: "2026-07-25T11:30:00Z",
          aggregate_score: 60,
          aggregate_priority: "medium",
        },
        {
          assessment_id: "risk-1",
          evaluation_time: "2026-07-25T12:30:00Z",
          aggregate_score: 72,
          aggregate_priority: "high",
        },
      ],
    },
    account_risk_heatmap: [
      {
        aws_account_id: "account-1",
        account_display_identifier: "Account primary",
        score: 72,
        priority: "high",
        findings_total: 5,
        critical_count: 1,
        high_count: 1,
      },
    ],
    freshness: {
      latest_completed_discovery: {
        id: "discovery-1",
        status: "completed",
        started_at: "2026-07-25T10:00:00Z",
        finished_at: "2026-07-25T10:05:00Z",
        evaluation_time: null,
      },
      latest_discovery: null,
      latest_completed_evaluation: {
        id: "evaluation-1",
        status: "completed",
        started_at: "2026-07-25T10:10:00Z",
        finished_at: "2026-07-25T10:15:00Z",
        evaluation_time: null,
      },
      latest_evaluation: null,
      latest_completed_compliance_assessment: {
        id: "assessment-1",
        status: "completed",
        started_at: "2026-07-25T10:50:00Z",
        finished_at: "2026-07-25T11:00:00Z",
        evaluation_time: null,
      },
      latest_compliance_assessment: null,
      latest_completed_risk_assessment: {
        id: "risk-1",
        status: "completed",
        started_at: null,
        finished_at: "2026-07-25T12:30:00Z",
        evaluation_time: "2026-07-25T12:30:00Z",
      },
      latest_risk_assessment: null,
    },
  };
}

function renderAt(path: string, me: Me | null) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const view = render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <AuthProvider initialMe={me} restoreOnMount={false}>
          <App />
        </AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return { ...view, client };
}

describe("SecurityDashboardPage", () => {
  it("shows a loading state before the summary resolves", async () => {
    const me = meFor("org-loading");
    vi.stubGlobal(
      "fetch",
      vi.fn(
        () =>
          new Promise(() => {
            /* never resolves during this assertion window */
          }),
      ),
    );
    renderAt("/security-dashboard", me);
    expect(
      await screen.findByText(/loading security posture/i),
    ).toBeInTheDocument();
  });

  it("renders populated dashboard sections from the Stage 8A API contract", async () => {
    const me = meFor("org-populated");
    const fetchMock = vi.fn(async () => {
      return new Response(JSON.stringify(populatedSummary("org-populated")), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    });
    vi.stubGlobal("fetch", fetchMock);
    renderAt("/security-dashboard", me);

    expect(
      await screen.findByRole("heading", { name: "Security posture" }),
    ).toBeInTheDocument();
    const riskSummary = await screen.findByRole("region", { name: "Risk" });
    expect(within(riskSummary).getByText("72")).toBeInTheDocument();
    expect(screen.getByText("70%")).toBeInTheDocument();
    expect(screen.getByText("EC2_SG_SSH_OPEN_TO_WORLD")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining(
        "/api/v1/dashboard/summary?organization_id=org-populated",
      ),
      expect.anything(),
    );
  });

  it("shows a partial-data warning with missing sections when data is incomplete", async () => {
    const me = meFor("org-empty");
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        return new Response(JSON.stringify(emptySummary("org-empty")), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }),
    );
    renderAt("/security-dashboard", me);

    expect(await screen.findByRole("status")).toHaveTextContent(
      /partial data/i,
    );
    expect(
      screen.getByText(/no completed compliance assessment/i),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/no completed risk assessment/i),
    ).toBeInTheDocument();
  });

  it("shows a safe error state and allows retry on API failure", async () => {
    const me = meFor("org-error");
    let callCount = 0;
    const fetchMock = vi.fn(async () => {
      callCount += 1;
      if (callCount === 1) {
        return new Response(JSON.stringify({ detail: "boom" }), {
          status: 500,
          headers: { "Content-Type": "application/json" },
        });
      }
      return new Response(JSON.stringify(populatedSummary("org-error")), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    });
    vi.stubGlobal("fetch", fetchMock);
    renderAt("/security-dashboard", me);

    expect(
      await screen.findByText(/unable to load the security dashboard/i),
    ).toBeInTheDocument();

    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /retry/i }));

    expect(
      await screen.findByRole("heading", { name: "Security posture" }),
    ).toBeInTheDocument();
  });

  it("isolates dashboard state across an organization switch and does not render stale data", async () => {
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("organization_id=org-a")) {
        return new Response(JSON.stringify(populatedSummary("org-a")), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }
      if (url.includes("organization_id=org-b")) {
        return new Response(JSON.stringify(emptySummary("org-b")), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }
      return new Response("[]", { status: 200 });
    });
    vi.stubGlobal("fetch", fetchMock);

    // AuthProvider seeds its `me` state from the `initialMe` prop via
    // useState, which React only consults on a component's first mount.
    // Rerendering the same AuthProvider element with a new `initialMe`
    // value does not update its internal state, so a real organization
    // switch must remount the provider (a fresh `key` forces this) rather
    // than merely rerendering it with different props. The same QueryClient
    // instance is kept across both renders so this still exercises real
    // per-organization cache isolation, not a full app reset.
    const { rerender } = render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={["/security-dashboard"]}>
          <AuthProvider
            key="org-a"
            initialMe={meFor("org-a")}
            restoreOnMount={false}
          >
            <App />
          </AuthProvider>
        </MemoryRouter>
      </QueryClientProvider>,
    );
    const riskSummaryA = await screen.findByRole("region", { name: "Risk" });
    expect(within(riskSummaryA).getByText("72")).toBeInTheDocument();

    rerender(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={["/security-dashboard"]}>
          <AuthProvider
            key="org-b"
            initialMe={meFor("org-b")}
            restoreOnMount={false}
          >
            <App />
          </AuthProvider>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    await waitFor(() => {
      const riskSummaryB = screen.getByRole("region", { name: "Risk" });
      expect(within(riskSummaryB).queryByText("72")).not.toBeInTheDocument();
    });
    expect(
      await screen.findByText(/no completed risk assessment/i),
    ).toBeInTheDocument();

    // Prove a real, distinct request for org-b's own data was made rather
    // than the UI merely continuing to display org-a's cached result.
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("organization_id=org-b"),
      expect.anything(),
    );
  });

  it("clears the query cache on logout so protected dashboard state cannot leak", async () => {
    const me = meFor("org-logout");
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/auth/logout")) {
        return new Response(null, { status: 204 });
      }
      return new Response(JSON.stringify(populatedSummary("org-logout")), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    });
    vi.stubGlobal("fetch", fetchMock);
    const { client } = renderAt("/security-dashboard", me);

    const riskSummary = await screen.findByRole("region", { name: "Risk" });
    expect(within(riskSummary).getByText("72")).toBeInTheDocument();
    expect(client.getQueryCache().getAll().length).toBeGreaterThan(0);

    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /logout/i }));

    await waitFor(() => {
      expect(client.getQueryCache().getAll().length).toBe(0);
    });
  });

  it("navigates to the security dashboard from the primary navigation", async () => {
    const me = meFor("org-nav");
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/api/v1/dashboard/summary")) {
        return new Response(JSON.stringify(populatedSummary("org-nav")), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }
      // The Stage 1 landing page (/dashboard) requests members, invitations,
      // and audit events, each of which is an array-shaped response.
      return new Response("[]", {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    });
    vi.stubGlobal("fetch", fetchMock);
    renderAt("/dashboard", me);
    expect(
      await screen.findByRole("heading", { name: `Organization org-nav` }),
    ).toBeInTheDocument();
    const user = userEvent.setup();
    await user.click(screen.getByRole("link", { name: /security posture/i }));
    expect(
      await screen.findByRole("heading", { name: "Security posture" }),
    ).toBeInTheDocument();
  });
});
