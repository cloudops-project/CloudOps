import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { App } from "../App";
import { AuthProvider } from "../auth/AuthProvider";
import type { Me } from "../types";

const owner: Me = {
  user: {
    id: "u1",
    email: "owner@example.com",
    full_name: "Owner",
    status: "active",
  },
  organizations: [
    {
      id: "o1",
      name: "Example Org",
      slug: "example",
      role: "owner",
    },
  ],
};
function renderApp(path: string, me: Me | null = null) {
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

describe("Stage 1 application", () => {
  it("restores authentication using refresh and profile requests", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      const data = url.includes("/auth/refresh")
        ? { access_token: "access-token" }
        : url.includes("/auth/me")
          ? owner
          : [];
      return new Response(JSON.stringify(data), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    });
    vi.stubGlobal("fetch", fetchMock);
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={["/dashboard"]}>
          <AuthProvider>
            <App />
          </AuthProvider>
        </MemoryRouter>
      </QueryClientProvider>,
    );
    expect(screen.getByText(/restoring session/i)).toBeInTheDocument();
    expect(
      await screen.findByRole("heading", { name: "Example Org" }),
    ).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/api/v1/auth/refresh"),
      expect.objectContaining({ credentials: "include" }),
    );
  });

  it("redirects to login after failed authentication restoration", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(null, { status: 401 })),
    );
    const client = new QueryClient();
    render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={["/dashboard"]}>
          <AuthProvider>
            <App />
          </AuthProvider>
        </MemoryRouter>
      </QueryClientProvider>,
    );
    expect(
      await screen.findByRole("heading", { name: /welcome back/i }),
    ).toBeInTheDocument();
  });
  it("clears an authenticated user when token refresh fails", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(null, { status: 401 })),
    );
    renderApp("/dashboard", owner);
    expect(
      await screen.findByRole("heading", { name: /welcome back/i }),
    ).toBeInTheDocument();
  });
  it("validates registration and supports keyboard submission", async () => {
    renderApp("/register");
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /create account/i }));
    expect(
      await screen.findByText(/use at least 12 characters/i),
    ).toBeInTheDocument();
    expect(screen.getByLabelText(/full name/i)).toBeVisible();
  });
  it("shows safe field-specific backend registration validation", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
        const payload = JSON.parse(String(init?.body)) as Record<
          string,
          unknown
        >;
        expect(payload).not.toHaveProperty("organization_name");
        return new Response(
          JSON.stringify({
            error: {
              code: "validation_error",
              message: "Request validation failed.",
              details: [
                {
                  field: "body.email",
                  message: "Use a deliverable email domain.",
                },
              ],
            },
          }),
          {
            status: 422,
            headers: { "Content-Type": "application/json" },
          },
        );
      }),
    );
    renderApp("/register");
    await userEvent.type(screen.getByLabelText("Full name"), "Test User");
    await userEvent.type(screen.getByLabelText("Email"), "user@example.com");
    await userEvent.type(
      screen.getByLabelText("Password"),
      "Strong-Password-123!",
    );
    await userEvent.click(
      screen.getByRole("button", { name: "Create account" }),
    );
    expect(
      await screen.findByText("Use a deliverable email domain."),
    ).toBeInTheDocument();
    expect(
      screen.queryByText("Request validation failed."),
    ).not.toBeInTheDocument();
  });
  it("validates login", async () => {
    renderApp("/login");
    await userEvent.click(screen.getByRole("button", { name: /sign in/i }));
    expect(await screen.findByText(/enter a valid email/i)).toBeInTheDocument();
    expect(screen.getByText(/password is required/i)).toBeInTheDocument();
  });
  it("redirects a signed-out user from protected routes", async () => {
    renderApp("/dashboard");
    expect(
      await screen.findByRole("heading", { name: /welcome back/i }),
    ).toBeInTheDocument();
  });
  it("renders unauthorized and not-found states", async () => {
    const first = renderApp("/unauthorized");
    expect(
      screen.getByRole("heading", { name: /access denied/i }),
    ).toBeInTheDocument();
    first.unmount();
    renderApp("/does-not-exist");
    expect(
      screen.getByRole("heading", { name: /page not found/i }),
    ).toBeInTheDocument();
  });
  it("renders organization creation and profile", async () => {
    const first = renderApp("/organizations/new", owner);
    expect(
      screen.getByRole("heading", { name: /create organization/i }),
    ).toBeInTheDocument();
    first.unmount();
    renderApp("/profile", owner);
    expect(screen.getAllByText("owner@example.com")).toHaveLength(2);
    expect(
      screen.getByRole("button", { name: /change password/i }),
    ).toBeInTheDocument();
  });
  it("renders dashboard loading then member and activity data", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        const data = url.includes("/members")
          ? [
              {
                id: "m1",
                email: "owner@example.com",
                full_name: "Owner",
                role: "owner",
                status: "active",
              },
            ]
          : url.includes("/invitations")
            ? []
            : url.includes("/audit-events")
              ? []
              : [];
        return new Response(JSON.stringify(data), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }),
    );
    renderApp("/dashboard", owner);
    expect(screen.getByText(/loading dashboard/i)).toBeInTheDocument();
    await waitFor(() =>
      expect(screen.getByText("Total members")).toBeInTheDocument(),
    );
    expect(
      screen.getByRole("link", { name: /invite member/i }),
    ).toBeInTheDocument();
    expect(screen.getByText(/no recent activity/i)).toBeInTheDocument();
  });
  it("shows owner role controls and invitation form", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async () =>
          new Response(
            JSON.stringify([
              {
                id: "m1",
                email: "owner@example.com",
                full_name: "Owner",
                role: "owner",
                status: "active",
              },
            ]),
            { status: 200, headers: { "Content-Type": "application/json" } },
          ),
      ),
    );
    const first = renderApp("/members", owner);
    expect(await screen.findByLabelText(/role for owner/i)).toBeInTheDocument();
    first.unmount();
    renderApp("/members/invite", owner);
    expect(
      screen.getByRole("heading", { name: /invite member/i }),
    ).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: /role/i })).toBeInTheDocument();
  });
  it("accepts an invitation token form", async () => {
    renderApp(
      "/invitations/accept?token=development-token-value-that-is-long-enough",
      owner,
    );
    expect(screen.getByLabelText(/invitation token/i)).toHaveValue(
      "development-token-value-that-is-long-enough",
    );
    expect(
      screen.getByRole("button", { name: /accept invitation/i }),
    ).toBeEnabled();
  });

  it("logs out and makes protected content inaccessible", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) =>
        String(input).includes("/auth/logout")
          ? new Response(null, { status: 204 })
          : new Response(JSON.stringify([]), {
              status: 200,
              headers: { "Content-Type": "application/json" },
            }),
      ),
    );
    renderApp("/dashboard", owner);
    await userEvent.click(screen.getByRole("button", { name: /logout/i }));
    expect(
      await screen.findByRole("heading", { name: /welcome back/i }),
    ).toBeInTheDocument();
  });

  it("submits an invitation and exposes the development token", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async () =>
          new Response(
            JSON.stringify({
              id: "i1",
              email: "new@example.com",
              role: "viewer",
              status: "pending",
              development_token: "one-time-development-token-value",
            }),
            { status: 201, headers: { "Content-Type": "application/json" } },
          ),
      ),
    );
    renderApp("/members/invite", owner);
    await userEvent.type(screen.getByLabelText(/email/i), "new@example.com");
    await userEvent.click(
      screen.getByRole("button", { name: /send invitation/i }),
    );
    expect(
      await screen.findByText("one-time-development-token-value"),
    ).toBeInTheDocument();
  });
});

describe("Stage 5 compliance", () => {
  const framework = {
    id: "framework-1",
    key: "cis_aws",
    name: "CIS AWS Foundations",
    version: "1.5",
    description: "CloudOps-authored summary.",
    official_reference: "https://example.invalid/cis",
    enabled: true,
  };
  const awsAccount = {
    id: "account-1",
    organization_id: "o1",
    name: "Production",
    account_id: "123456789012",
    role_arn: "arn:aws:iam::123456789012:role/CloudOpsReadOnlyRole",
    external_id: "test-external-id",
    status: "connected",
    connection_status: "connected",
    failure_reason: null,
    last_validated_at: null,
  };

  it("confirms an assessment once and restores focus", async () => {
    const fetchMock = vi.fn(
      async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        const isAssessmentPost =
          url.includes("/compliance/assess") && init?.method === "POST";
        const data = isAssessmentPost
          ? {}
          : url.includes("/compliance/frameworks")
            ? [framework]
            : url.includes("/aws/accounts")
              ? [awsAccount]
              : { items: [], total: 0, page: 1, page_size: 25 };
        return new Response(JSON.stringify(data), {
          status: isAssessmentPost ? 201 : 200,
          headers: { "Content-Type": "application/json" },
        });
      },
    );
    vi.stubGlobal("fetch", fetchMock);
    renderApp("/compliance", owner);
    const trigger = await screen.findByRole("button", {
      name: /run assessment/i,
    });
    await userEvent.click(trigger);
    expect(
      screen.getByRole("dialog", { name: /run compliance assessment/i }),
    ).toBeInTheDocument();
    await userEvent.selectOptions(
      screen.getByLabelText(/aws account/i),
      awsAccount.id,
    );
    await userEvent.selectOptions(
      screen.getByLabelText(/framework/i),
      framework.id,
    );
    const confirm = screen.getByRole("button", {
      name: /confirm assessment/i,
    });
    await userEvent.dblClick(confirm);
    await waitFor(() =>
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument(),
    );
    expect(
      fetchMock.mock.calls.filter(
        ([input, init]) =>
          String(input).includes("/compliance/assess") &&
          init?.method === "POST",
      ),
    ).toHaveLength(1);
    expect(trigger).toHaveFocus();
  });

  it.each([
    ["owner", true],
    ["admin", true],
    ["security_analyst", true],
    ["cloud_engineer", true],
    ["auditor", false],
    ["viewer", false],
  ] as const)("applies assessment controls for %s", async (role, allowed) => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const data = String(input).includes("/compliance/frameworks")
          ? [framework]
          : String(input).includes("/aws/accounts")
            ? [awsAccount]
            : { items: [], total: 0, page: 1, page_size: 25 };
        return new Response(JSON.stringify(data), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }),
    );
    renderApp("/compliance", {
      ...owner,
      organizations: [{ ...owner.organizations[0], role }],
    });
    await screen.findByRole("heading", { name: "Compliance" });
    const trigger = screen.queryByRole("button", { name: /run assessment/i });
    if (allowed) expect(trigger).toBeInTheDocument();
    else expect(trigger).not.toBeInTheDocument();
  });

  it("renders framework and control detail with escaped CloudOps text", async () => {
    const control = {
      id: "control-1",
      framework_id: framework.id,
      control_key: "1.1",
      title: "<script>Control title</script>",
      description: "CloudOps summary, not official wording.",
      section: "Identity",
    };
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        const data = url.includes("/controls/control-1/rules")
          ? [
              {
                id: "mapping-1",
                rule_key: "IAM_USER_CONSOLE_ACCESS_WITHOUT_MFA",
                minimum_rule_version: 1,
                maximum_rule_version: null,
                framework_id: framework.id,
                control_id: control.id,
                mapping_type: "detective",
                rationale: "MFA evidence supports this control.",
              },
            ]
          : url.includes("/controls/control-1/findings")
            ? {
                control,
                status: "fail",
                finding_ids: [],
                total: 0,
                page: 1,
                page_size: 25,
              }
            : url.includes("/controls/control-1")
              ? control
              : url.includes("/frameworks/cis_aws/controls")
                ? [control]
                : url.includes("/compliance/frameworks")
                  ? [framework]
                  : [];
        return new Response(JSON.stringify(data), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }),
    );
    const frameworkView = renderApp("/compliance/frameworks/cis_aws", owner);
    expect(
      await screen.findByRole("heading", { name: framework.name }),
    ).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText(/search controls/i), "1.1");
    expect(screen.getByRole("link", { name: "1.1" })).toBeInTheDocument();
    frameworkView.unmount();

    renderApp("/compliance/controls/control-1", owner);
    expect(
      await screen.findByRole("heading", {
        name: /<script>control title<\/script>/i,
      }),
    ).toBeInTheDocument();
    expect(document.querySelector("script")).toBeNull();
    expect(
      screen.getByText("IAM_USER_CONSOLE_ACCESS_WITHOUT_MFA"),
    ).toBeInTheDocument();
    expect(screen.getByText(/MFA evidence supports/i)).toBeInTheDocument();
    expect(screen.getByText(/No mapped findings/i)).toBeInTheDocument();
  });

  it("filters and paginates assessment history", async () => {
    const assessment = {
      id: "assessment-1",
      organization_id: "o1",
      aws_account_id: awsAccount.id,
      framework_id: framework.id,
      evaluation_job_id: "evaluation-1",
      status: "completed",
      controls_total: 4,
      controls_passed: 1,
      controls_failed: 1,
      controls_not_assessed: 1,
      controls_error: 1,
      findings_count: 1,
      started_at: "2026-07-24T00:00:00Z",
      finished_at: "2026-07-24T00:01:00Z",
      error_summary: null,
    };
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      const data = url.includes("/compliance/frameworks")
        ? [framework]
        : url.includes("/aws/accounts")
          ? [awsAccount]
          : { items: [assessment], total: 11, page: 1, page_size: 10 };
      return new Response(JSON.stringify(data), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    });
    vi.stubGlobal("fetch", fetchMock);
    renderApp("/compliance/assessments", owner);
    expect(
      await screen.findByRole("heading", { name: /compliance assessments/i }),
    ).toBeInTheDocument();
    await userEvent.selectOptions(
      screen.getByLabelText(/assessment status/i),
      "completed",
    );
    await userEvent.click(
      screen.getByRole("button", { name: /next assessment page/i }),
    );
    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining("page=2"),
        expect.anything(),
      ),
    );
    expect(screen.getByText("Page 2")).toBeInTheDocument();
  });

  it("renders immutable assessment snapshots and status filtering", async () => {
    const detail = {
      id: "assessment-1",
      organization_id: "o1",
      aws_account_id: awsAccount.id,
      framework_id: framework.id,
      evaluation_job_id: "evaluation-1",
      status: "completed",
      controls_total: 1,
      controls_passed: 0,
      controls_failed: 1,
      controls_not_assessed: 0,
      controls_error: 0,
      findings_count: 1,
      started_at: "2026-07-24T00:00:00Z",
      finished_at: "2026-07-24T00:01:00Z",
      error_summary: null,
      controls: [
        {
          id: "snapshot-1",
          assessment_id: "assessment-1",
          control_id: "control-1",
          framework_id: framework.id,
          status: "fail",
          findings_count: 1,
          assessed_at: "2026-07-24T00:01:00Z",
        },
      ],
    };
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async () =>
          new Response(JSON.stringify(detail), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          }),
      ),
    );
    renderApp("/compliance/assessments/assessment-1", owner);
    expect(
      await screen.findByText(/immutable snapshot does not change/i),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Source evaluation: evaluation-1"),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("columnheader", { name: "Status" }),
    ).toBeInTheDocument();
    await userEvent.selectOptions(
      screen.getByLabelText(/control status/i),
      "fail",
    );
    expect(screen.getByText("Status: fail")).toBeInTheDocument();
  });

  it("cancels and closes assessment confirmation with Escape", async () => {
    const fetchMock = vi.fn(
      async (input: RequestInfo | URL, _init?: RequestInit) => {
        void _init;
        const url = String(input);
        const data = url.includes("/compliance/frameworks")
          ? [framework]
          : url.includes("/aws/accounts")
            ? [awsAccount]
            : url.includes("/summary")
              ? {
                  assessments_total: 0,
                  controls_passed: 0,
                  controls_failed: 0,
                  controls_not_assessed: 0,
                  controls_error: 0,
                }
              : { items: [], total: 0, page: 1, page_size: 5 };
        return new Response(JSON.stringify(data), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      },
    );
    vi.stubGlobal("fetch", fetchMock);
    renderApp("/compliance", owner);
    const trigger = await screen.findByRole("button", {
      name: /run assessment/i,
    });
    await userEvent.click(trigger);
    expect(
      screen.getByRole("button", { name: /confirm assessment/i }),
    ).toHaveFocus();
    await userEvent.click(screen.getByRole("button", { name: /cancel/i }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
    await userEvent.click(trigger);
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
    expect(
      fetchMock.mock.calls.filter(
        ([input, init]) =>
          String(input).includes("/compliance/assess") &&
          init?.method === "POST",
      ),
    ).toHaveLength(0);
  });
});

describe("Stage 4 deterministic findings", () => {
  const account = {
    id: "a1",
    organization_id: "o1",
    name: "Production",
    account_id: "123456789012",
    role_arn: "arn:aws:iam::123456789012:role/CloudOpsReadOnlyRole",
    external_id: "test-external-id",
    status: "connected",
    connection_status: "connected",
    failure_reason: null,
    last_validated_at: null,
  };
  const finding = {
    id: "f1",
    organization_id: "o1",
    aws_account_id: "a1",
    asset_id: "asset1",
    rule_key: "EC2_SG_SSH_OPEN_TO_WORLD",
    rule_version: 1,
    severity: "critical",
    category: "network",
    service: "ec2",
    asset_type: "ec2_security_group",
    region: "us-east-1",
    remediation: "Restrict SSH access.",
    references: ["https://docs.aws.amazon.com/"],
    status: "open",
    evidence: { cidr: "<script>alert('unsafe')</script>" },
    first_seen_at: "2026-07-23T00:00:00Z",
    last_seen_at: "2026-07-23T00:00:00Z",
    resolved_at: null,
    suppressed_at: null,
    suppressed_until: null,
    suppression_reason: null,
    last_evaluation_id: "e1",
  };

  it("renders severity counts and escaped finding evidence", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        const data = url.includes("/summary")
          ? {
              total: 1,
              items: [
                {
                  severity: "critical",
                  status: "open",
                  service: "ec2",
                  aws_account_id: "a1",
                  asset_type: "ec2_security_group",
                  region: "us-east-1",
                  count: 1,
                },
              ],
            }
          : finding;
        return new Response(JSON.stringify(data), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }),
    );
    const dashboard = renderApp("/security", owner);
    expect((await screen.findAllByText("1")).length).toBeGreaterThanOrEqual(1);
    dashboard.unmount();
    renderApp("/findings/f1", owner);
    expect(
      await screen.findByText("<script>alert('unsafe')</script>", {
        exact: false,
      }),
    ).toBeInTheDocument();
    expect(document.querySelector("script")).toBeNull();
  });

  it("filters and paginates findings", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      const data = url.includes("/aws/accounts")
        ? [account]
        : { items: [finding], total: 30, page: 1, page_size: 25 };
      return new Response(JSON.stringify(data), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    });
    vi.stubGlobal("fetch", fetchMock);
    renderApp("/findings", owner);
    const user = userEvent.setup();
    await screen.findByText("EC2_SG_SSH_OPEN_TO_WORLD");
    await user.selectOptions(screen.getByLabelText("AWS account"), "a1");
    await user.selectOptions(screen.getByLabelText("Service"), "ec2");
    await user.selectOptions(
      screen.getByLabelText("Asset type"),
      "ec2_security_group",
    );
    await user.selectOptions(screen.getByLabelText("Severity"), "critical");
    await user.selectOptions(screen.getByLabelText("Status"), "open");
    await user.type(screen.getByLabelText("Region"), "us-east-1");
    await user.type(screen.getByLabelText("Rule"), "EC2_SG_SSH_OPEN_TO_WORLD");
    await user.type(screen.getByLabelText("Asset ID"), "asset1");
    await user.type(screen.getByLabelText("Search findings"), "ssh");
    await user.click(screen.getByRole("button", { name: "Next" }));
    await waitFor(() => {
      const urls = fetchMock.mock.calls.map(([input]) => String(input));
      const url = urls.find((value) => value.includes("/findings?")) ?? "";
      for (const expected of [
        "aws_account_id=a1",
        "service=ec2",
        "asset_type=ec2_security_group",
        "severity=critical",
        "status=open",
        "region=us-east-1",
        "rule_key=EC2_SG_SSH_OPEN_TO_WORLD",
        "asset_id=asset1",
        "search=ssh",
        "page=2",
      ]) {
        expect(urls.some((value) => value.includes(expected))).toBe(true);
      }
      expect(url).toContain("organization_id=");
    });
  });

  it("requires a suppression reason and restores dialog focus", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const suppressed = init?.method === "POST";
        return new Response(
          JSON.stringify(
            suppressed ? { ...finding, status: "suppressed" } : finding,
          ),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }),
    );
    renderApp("/findings/f1", owner);
    const user = userEvent.setup();
    const trigger = await screen.findByRole("button", {
      name: "Suppress finding",
    });
    await user.click(trigger);
    const dialog = screen.getByRole("dialog", { name: "Suppress finding" });
    expect(dialog).toBeInTheDocument();
    const confirm = screen.getByRole("button", { name: "Confirm suppression" });
    expect(confirm).toBeDisabled();
    await user.type(screen.getByLabelText("Suppression reason"), "Maintenance");
    expect(confirm).toBeEnabled();
    await user.keyboard("{Shift>}{Tab}{/Shift}");
    expect(confirm).toHaveFocus();
    await user.tab();
    expect(screen.getByLabelText("Suppression reason")).toHaveFocus();
    await user.keyboard("{Escape}");
    await waitFor(() => expect(trigger).toHaveFocus());
  });

  it.each([
    ["owner", true],
    ["admin", true],
    ["security_analyst", true],
    ["cloud_engineer", true],
    ["auditor", false],
    ["viewer", false],
  ] as const)("applies evaluation controls for %s", async (role, allowed) => {
    const me: Me = {
      ...owner,
      organizations: [{ ...owner.organizations[0], role: role }],
    };
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const data = String(input).includes("/aws/accounts")
          ? [account]
          : { items: [], total: 0, page: 1, page_size: 25 };
        return new Response(JSON.stringify(data), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }),
    );
    renderApp("/evaluations", me);
    await screen.findByText(/no evaluations yet/i);
    const trigger = screen.queryByRole("button", { name: /run evaluation/i });
    if (allowed) expect(trigger).toBeInTheDocument();
    else expect(trigger).not.toBeInTheDocument();
  });

  it("confirms an evaluation once and cancels without calling the API", async () => {
    const fetchMock = vi.fn(
      async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        const data = url.includes("/aws/accounts")
          ? [account]
          : url.includes("/evaluate") && init?.method === "POST"
            ? {
                id: "e1",
                status: "completed",
                sequence: 1,
              }
            : { items: [], total: 0, page: 1, page_size: 25 };
        return new Response(JSON.stringify(data), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      },
    );
    vi.stubGlobal("fetch", fetchMock);
    renderApp("/evaluations", owner);
    const user = userEvent.setup();
    await screen.findByRole("option", { name: "Production" });
    await user.selectOptions(screen.getByLabelText("AWS account"), "a1");
    await user.click(screen.getByRole("button", { name: "Run evaluation" }));
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(
      fetchMock.mock.calls.filter(([url]) => String(url).includes("/evaluate")),
    ).toHaveLength(0);
    await user.click(screen.getByRole("button", { name: "Run evaluation" }));
    await user.click(
      screen.getByRole("button", { name: "Confirm evaluation" }),
    );
    await waitFor(() =>
      expect(
        fetchMock.mock.calls.filter(([url]) =>
          String(url).includes("/evaluate"),
        ),
      ).toHaveLength(1),
    );
  });
});

describe("Stage 2 AWS account onboarding", () => {
  it("validates the create-account form before sending a request", async () => {
    renderApp("/aws/accounts/new", owner);
    await userEvent.click(
      screen.getByRole("button", { name: /generate onboarding setup/i }),
    );
    expect(
      await screen.findByText(/enter an account name/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/exactly 12 digits/i)).toBeInTheDocument();
  });

  it("shows accounts and their connection status", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async () =>
          new Response(
            JSON.stringify([
              {
                id: "a1",
                organization_id: "o1",
                name: "Production",
                account_id: "123456789012",
                role_arn: null,
                external_id: "cloudops-test",
                status: "connected",
                connection_status: "connected",
                failure_reason: null,
                last_validated_at: null,
              },
            ]),
            { status: 200, headers: { "Content-Type": "application/json" } },
          ),
      ),
    );
    renderApp("/aws/accounts", owner);
    expect(await screen.findByText("Production")).toBeInTheDocument();
    expect(screen.getByText("connected")).toBeInTheDocument();
    expect(screen.getByText("123456789012")).toBeInTheDocument();
  });

  it("validates a role ARN on account details", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async () =>
          new Response(
            JSON.stringify({
              account: {
                id: "a1",
                organization_id: "o1",
                name: "Production",
                account_id: "123456789012",
                role_arn: null,
                external_id: "cloudops-test",
                status: "pending",
                connection_status: "pending",
                failure_reason: null,
                last_validated_at: null,
              },
              trust_policy: {},
              permission_policy: {
                policy_name: "SecurityAudit",
                managed_policy_arn: "arn:aws:iam::aws:policy/SecurityAudit",
                description: "Read-only policy",
              },
              onboarding_instructions: ["Create the role."],
            }),
            { status: 200, headers: { "Content-Type": "application/json" } },
          ),
      ),
    );
    renderApp("/aws/accounts/a1", owner);
    const roleInput = await screen.findByLabelText(/aws iam role arn/i);
    await userEvent.type(roleInput, "not-an-arn");
    await userEvent.click(
      screen.getByRole("button", { name: /save role arn/i }),
    );
    expect(await screen.findByText(/valid iam role arn/i)).toBeInTheDocument();
  });

  it("rejects non-admin users from onboarding routes", async () => {
    const viewer: Me = {
      ...owner,
      organizations: [{ ...owner.organizations[0], role: "viewer" }],
    };
    renderApp("/aws/accounts/new", viewer);
    expect(
      await screen.findByRole("heading", { name: /access denied/i }),
    ).toBeInTheDocument();
  });
});

describe("Stage 3 asset discovery", () => {
  const account = {
    id: "a1",
    organization_id: "o1",
    name: "Production",
    account_id: "123456789012",
    role_arn: "arn:aws:iam::123456789012:role/CloudOpsReadOnlyRole",
    external_id: "cloudops-test",
    status: "connected",
    connection_status: "connected",
    failure_reason: null,
    last_validated_at: null,
  };
  const asset = {
    id: "asset1",
    organization_id: "o1",
    aws_account_id: "a1",
    asset_type: "ec2_instance",
    resource_id: "i-123",
    arn: "arn:aws:ec2:us-east-1:123456789012:instance/i-123",
    name: "web-server",
    region: "us-east-1",
    status: "running",
    tags: { Environment: "test" },
    metadata: {
      instance_type: "t3.micro",
      untrusted: "<script>alert('xss')</script>",
    },
    first_seen_at: "2026-01-01T00:00:00Z",
    last_seen_at: "2026-01-02T00:00:00Z",
    is_active: true,
  };

  it("lists, filters, and paginates normalized assets", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      return new Response(
        JSON.stringify(
          url.includes("/aws/accounts")
            ? [account]
            : { items: [asset], total: 26, page: 1, page_size: 25 },
        ),
        { status: 200, headers: { "Content-Type": "application/json" } },
      );
    });
    vi.stubGlobal("fetch", fetchMock);
    renderApp("/assets", owner);
    expect(await screen.findByText("web-server")).toBeInTheDocument();
    expect(screen.getAllByText("Active")).toHaveLength(2);
    await userEvent.type(screen.getByLabelText(/search assets/i), "web");
    await userEvent.selectOptions(screen.getByLabelText(/aws account/i), "a1");
    await userEvent.selectOptions(
      screen.getByLabelText(/asset type/i),
      "ec2_instance",
    );
    await userEvent.type(screen.getByLabelText(/^region$/i), "us-east-1");
    await userEvent.type(screen.getByLabelText(/^status$/i), "running");
    await userEvent.selectOptions(screen.getByLabelText(/lifecycle/i), "true");
    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringMatching(
          /aws_account_id=a1.*asset_type=ec2_instance.*region=us-east-1.*status=running.*is_active=true.*search=web/,
        ),
        expect.anything(),
      ),
    );
    const next = screen.getByRole("button", { name: /next/i });
    expect(next).toBeEnabled();
    expect(screen.getByRole("button", { name: /previous/i })).toBeDisabled();
    await userEvent.click(next);
    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining("page=2"),
        expect.anything(),
      ),
    );
  });

  it("shows normalized fields, tags, and service metadata", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async () =>
          new Response(JSON.stringify(asset), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          }),
      ),
    );
    renderApp("/assets/asset1", owner);
    expect(await screen.findByText("web-server")).toBeInTheDocument();
    expect(screen.getByText("Tags")).toBeInTheDocument();
    expect(screen.getByText("Service metadata")).toBeInTheDocument();
    expect(screen.getByText(/t3.micro/i)).toBeInTheDocument();
    expect(
      screen.getByText(/<script>alert\('xss'\)<\/script>/i),
    ).toBeInTheDocument();
    expect(document.querySelector("script")).toBeNull();
  });

  it("renders asset loading, empty, error, and stale states", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        if (String(input).includes("/aws/accounts"))
          return new Response(JSON.stringify([account]), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          });
        return await new Promise<Response>(() => undefined);
      }),
    );
    const loading = renderApp("/assets", owner);
    expect(screen.getByText(/loading assets/i)).toBeInTheDocument();
    loading.unmount();

    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const data = String(input).includes("/aws/accounts")
          ? [account]
          : { items: [], total: 0, page: 1, page_size: 25 };
        return new Response(JSON.stringify(data), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }),
    );
    const empty = renderApp("/assets", owner);
    expect(
      await screen.findByText(/no assets match these filters/i),
    ).toBeInTheDocument();
    empty.unmount();

    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) =>
        String(input).includes("/aws/accounts")
          ? new Response(JSON.stringify([account]), {
              status: 200,
              headers: { "Content-Type": "application/json" },
            })
          : new Response(JSON.stringify({ error: { message: "safe" } }), {
              status: 503,
              headers: { "Content-Type": "application/json" },
            }),
      ),
    );
    const error = renderApp("/assets", owner);
    expect(
      await screen.findByText(/unable to load assets/i),
    ).toBeInTheDocument();
    error.unmount();

    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const data = String(input).includes("/aws/accounts")
          ? [account]
          : {
              items: [{ ...asset, id: "stale", is_active: false }],
              total: 1,
              page: 1,
              page_size: 25,
            };
        return new Response(JSON.stringify(data), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }),
    );
    renderApp("/assets", owner);
    expect(await screen.findByText("Stale")).toBeInTheDocument();
  });

  it("starts discovery and renders partial results and sanitized errors", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      const data = url.includes("/aws/accounts/a1/discover")
        ? {
            id: "j2",
            aws_account_id: "a1",
            status: "pending",
            assets_discovered: 0,
            assets_created: 0,
            assets_updated: 0,
            assets_deactivated: 0,
          }
        : url.includes("/aws/accounts")
          ? [account]
          : {
              items: [
                {
                  id: "j1",
                  aws_account_id: "a1",
                  status: "partially_completed",
                  assets_discovered: 5,
                  assets_created: 4,
                  assets_updated: 1,
                  assets_deactivated: 0,
                  error_summary: "rds:accessdenied",
                },
              ],
              total: 1,
              page: 1,
              page_size: 25,
            };
      return new Response(JSON.stringify(data), {
        status: url.includes("/discover") ? 201 : 200,
        headers: { "Content-Type": "application/json" },
      });
    });
    vi.stubGlobal("fetch", fetchMock);
    renderApp("/discovery/jobs", owner);
    expect(await screen.findByText("partially completed")).toBeInTheDocument();
    expect(screen.getByText("rds:accessdenied")).toBeInTheDocument();
    await userEvent.selectOptions(
      screen.getByLabelText(/connected account/i),
      "a1",
    );
    await userEvent.click(
      screen.getByRole("button", { name: /run discovery/i }),
    );
    const dialog = screen.getByRole("dialog", {
      name: /confirm inventory discovery/i,
    });
    expect(dialog).toHaveTextContent("Production");
    expect(dialog).toHaveTextContent("123456789012");
    expect(
      screen.getByRole("button", { name: /confirm discovery/i }),
    ).toHaveFocus();
    expect(fetchMock).not.toHaveBeenCalledWith(
      expect.stringContaining("/aws/accounts/a1/discover"),
      expect.anything(),
    );
    await userEvent.dblClick(
      screen.getByRole("button", { name: /confirm discovery/i }),
    );
    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining("/aws/accounts/a1/discover"),
        expect.objectContaining({ method: "POST" }),
      ),
    );
    expect(
      fetchMock.mock.calls.filter(([input]) =>
        new URL(String(input)).pathname.endsWith("/discover"),
      ),
    ).toHaveLength(1);
  });

  it("cancels discovery confirmation and returns focus to the trigger", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const data = String(input).includes("/aws/accounts")
        ? [account]
        : { items: [], total: 0, page: 1, page_size: 25 };
      return new Response(JSON.stringify(data), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    });
    vi.stubGlobal("fetch", fetchMock);
    renderApp("/discovery/jobs", owner);
    await screen.findByRole("option", { name: "Production" });
    await userEvent.selectOptions(
      screen.getByLabelText(/connected account/i),
      "a1",
    );
    const trigger = screen.getByRole("button", { name: /run discovery/i });
    await userEvent.click(trigger);
    await userEvent.click(screen.getByRole("button", { name: /cancel/i }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    await waitFor(() => expect(trigger).toHaveFocus());
    expect(
      fetchMock.mock.calls.filter(([input]) =>
        new URL(String(input)).pathname.endsWith("/discover"),
      ),
    ).toHaveLength(0);
  });

  it("closes discovery confirmation with Escape and restores trigger focus", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const data = String(input).includes("/aws/accounts")
          ? [account]
          : { items: [], total: 0, page: 1, page_size: 25 };
        return new Response(JSON.stringify(data), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }),
    );
    renderApp("/discovery/jobs", owner);
    await screen.findByRole("option", { name: "Production" });
    await userEvent.selectOptions(
      screen.getByLabelText(/connected account/i),
      "a1",
    );
    const trigger = screen.getByRole("button", { name: /run discovery/i });
    await userEvent.click(trigger);
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    await waitFor(() => expect(trigger).toHaveFocus());
  });

  it.each(["pending", "running", "completed", "failed"] as const)(
    "renders the %s discovery state",
    async (status) => {
      vi.stubGlobal(
        "fetch",
        vi.fn(async (input: RequestInfo | URL) => {
          const data = String(input).includes("/aws/accounts")
            ? [account]
            : {
                items: [
                  {
                    id: `job-${status}`,
                    aws_account_id: "a1",
                    status,
                    assets_discovered: status === "completed" ? 7 : 0,
                    assets_created: status === "completed" ? 7 : 0,
                    assets_updated: 0,
                    assets_deactivated: 0,
                    error_summary:
                      status === "failed" ? "ec2:aws_service_error" : null,
                  },
                ],
                total: 1,
                page: 1,
                page_size: 25,
              };
          return new Response(JSON.stringify(data), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          });
        }),
      );
      renderApp("/discovery/jobs", owner);
      expect(
        await screen.findByText(status.replace("_", " ")),
      ).toBeInTheDocument();
      if (status === "completed")
        expect(screen.getByText("Discovered: 7")).toBeInTheDocument();
      if (status === "failed")
        expect(screen.getByText("ec2:aws_service_error")).toBeInTheDocument();
    },
  );

  it("hides discovery controls from viewers while allowing inventory access", async () => {
    const viewer: Me = {
      ...owner,
      organizations: [{ ...owner.organizations[0], role: "viewer" }],
    };
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const data = String(input).includes("/aws/accounts")
          ? [account]
          : { items: [], total: 0, page: 1, page_size: 25 };
        return new Response(JSON.stringify(data), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }),
    );
    renderApp("/discovery/jobs", viewer);
    expect(await screen.findByText(/no discovery jobs/i)).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /run discovery/i }),
    ).not.toBeInTheDocument();
  });

  it.each([
    ["owner", true],
    ["admin", true],
    ["security_analyst", true],
    ["cloud_engineer", true],
    ["auditor", false],
    ["viewer", false],
  ] as const)("applies discovery controls for %s", async (role, allowed) => {
    const me: Me = {
      ...owner,
      organizations: [{ ...owner.organizations[0], role: role }],
    };
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const data = String(input).includes("/aws/accounts")
          ? [account]
          : { items: [], total: 0, page: 1, page_size: 25 };
        return new Response(JSON.stringify(data), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }),
    );
    renderApp("/discovery/jobs", me);
    await screen.findByText(/no discovery jobs/i);
    const trigger = screen.queryByRole("button", { name: /run discovery/i });
    if (allowed) expect(trigger).toBeInTheDocument();
    else expect(trigger).not.toBeInTheDocument();
  });
});
