import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { describe, expect, it, vi } from "vitest";
import { App } from "../App";
import { AuthProvider } from "../auth/AuthProvider";
import type { Me, Page, RemediationRequest } from "../types";

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

const cloudEngineer: Me = {
  user: {
    id: "u2",
    email: "engineer@example.com",
    full_name: "Engineer",
    status: "active",
  },
  organizations: [
    {
      id: "o1",
      name: "Example Org",
      slug: "example",
      role: "cloud_engineer",
    },
  ],
};

const viewer: Me = {
  user: {
    id: "u3",
    email: "viewer@example.com",
    full_name: "Viewer",
    status: "active",
  },
  organizations: [
    {
      id: "o1",
      name: "Example Org",
      slug: "example",
      role: "viewer",
    },
  ],
};

function pendingRequest(
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
    requested_at: "2026-07-25T00:00:00Z",
    approved_at: null,
    rejected_at: null,
    cancelled_at: null,
    executed_at: null,
    failed_at: null,
    created_at: "2026-07-25T00:00:00Z",
    updated_at: "2026-07-25T00:00:00Z",
    ...overrides,
  };
}

function renderRemediations(me: Me, fetchImpl: typeof fetch) {
  vi.stubGlobal("fetch", fetchImpl);
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={["/remediations"]}>
        <AuthProvider initialMe={me} restoreOnMount={false}>
          <App />
        </AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("Remediation page", () => {
  it("lists a pending-approval request and lets an owner approve it", async () => {
    let approved = false;
    const fetchMock = vi.fn(
      async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        if (url.includes("/remediations/r1/approve")) {
          approved = true;
          return new Response(
            JSON.stringify(
              pendingRequest({
                status: "approved",
                approved_at: "2026-07-25T01:00:00Z",
                approved_by_user_id: "u1",
              }),
            ),
            { status: 200, headers: { "Content-Type": "application/json" } },
          );
        }
        if (url.includes("/api/v1/remediations?")) {
          const body: Page<RemediationRequest> = {
            items: [
              approved
                ? pendingRequest({ status: "approved" })
                : pendingRequest(),
            ],
            total: 1,
            page: 1,
            page_size: 10,
          };
          return new Response(JSON.stringify(body), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          });
        }
        void init;
        return new Response(JSON.stringify([]), { status: 200 });
      },
    );
    renderRemediations(owner, fetchMock);

    expect(
      await screen.findByRole("heading", { name: "Remediation" }),
    ).toBeInTheDocument();
    expect(
      await screen.findByText("Remediate EC2_SG_SSH_OPEN_TO_WORLD"),
    ).toBeInTheDocument();
    expect(
      within(screen.getByRole("table")).getByText("pending approval"),
    ).toBeInTheDocument();

    const approveButton = await screen.findByRole("button", {
      name: "Approve",
    });
    await userEvent.click(approveButton);

    await waitFor(() => expect(approved).toBe(true));
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/api/v1/remediations/r1/approve"),
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("does not show approve or execute controls for a viewer", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/api/v1/remediations?")) {
        const body: Page<RemediationRequest> = {
          items: [pendingRequest()],
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
    renderRemediations(viewer, fetchMock);

    expect(
      await screen.findByText("Remediate EC2_SG_SSH_OPEN_TO_WORLD"),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Approve" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Execute" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Cancel" }),
    ).not.toBeInTheDocument();
  });

  it("lets a cloud engineer cancel their own pending request but not approve", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/api/v1/remediations?")) {
        const body: Page<RemediationRequest> = {
          items: [pendingRequest()],
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
    renderRemediations(cloudEngineer, fetchMock);

    expect(
      await screen.findByText("Remediate EC2_SG_SSH_OPEN_TO_WORLD"),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Approve" }),
    ).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Cancel" })).toBeInTheDocument();
  });

  it("shows an empty state when no remediation requests exist", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/api/v1/remediations?")) {
        const body: Page<RemediationRequest> = {
          items: [],
          total: 0,
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
    renderRemediations(owner, fetchMock);

    expect(
      await screen.findByText("No remediation requests."),
    ).toBeInTheDocument();
  });

  it("shows an API error state without crashing the page", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/api/v1/remediations?")) {
        return new Response(
          JSON.stringify({ error: { code: "server_error", message: "boom" } }),
          { status: 500, headers: { "Content-Type": "application/json" } },
        );
      }
      return new Response(JSON.stringify([]), { status: 200 });
    });
    renderRemediations(owner, fetchMock);

    expect(
      await screen.findByRole("heading", { name: "Remediation" }),
    ).toBeInTheDocument();
    expect(
      await screen.findByText("Unable to load remediation requests."),
    ).toBeInTheDocument();
  });

  it("surfaces a failed execute action without crashing the page", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/remediations/r1/execute")) {
        return new Response(
          JSON.stringify({
            error: {
              code: "remediation_invalid_transition",
              message:
                "Cannot execute a remediation request in status 'pending_approval'.",
            },
          }),
          { status: 409, headers: { "Content-Type": "application/json" } },
        );
      }
      if (url.includes("/api/v1/remediations?")) {
        const body: Page<RemediationRequest> = {
          items: [
            pendingRequest({
              status: "approved",
              approved_at: "2026-07-25T01:00:00Z",
            }),
          ],
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
    renderRemediations(owner, fetchMock);

    const executeButton = await screen.findByRole("button", {
      name: "Execute",
    });
    await userEvent.click(executeButton);

    expect(
      await screen.findByText(
        "Cannot execute a remediation request in status 'pending_approval'.",
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Remediation" }),
    ).toBeInTheDocument();
  });

  it("filters remediation requests by status", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/api/v1/remediations?")) {
        const body: Page<RemediationRequest> = {
          items: url.includes("status=succeeded")
            ? [
                pendingRequest({
                  id: "r2",
                  status: "succeeded",
                  attempt_count: 1,
                }),
              ]
            : [pendingRequest()],
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
    renderRemediations(owner, fetchMock);

    await screen.findByText("Remediate EC2_SG_SSH_OPEN_TO_WORLD");
    const select = screen.getByLabelText("Status");
    await userEvent.selectOptions(select, "succeeded");

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining("status=succeeded"),
        expect.anything(),
      ),
    );
  });

  it("shows a succeeded request without action controls", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/api/v1/remediations?")) {
        const body: Page<RemediationRequest> = {
          items: [
            pendingRequest({
              status: "succeeded",
              attempt_count: 1,
              approved_at: "2026-07-25T01:00:00Z",
              executed_at: "2026-07-25T01:05:00Z",
            }),
          ],
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
    renderRemediations(owner, fetchMock);

    expect(
      await screen.findByText("Remediate EC2_SG_SSH_OPEN_TO_WORLD"),
    ).toBeInTheDocument();
    expect(
      within(screen.getByRole("table")).getByText("Succeeded"),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Approve" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Execute" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Cancel" }),
    ).not.toBeInTheDocument();
  });
});
