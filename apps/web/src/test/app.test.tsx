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
      current_user_role: "owner",
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
      organizations: [
        { ...owner.organizations[0], current_user_role: "viewer" },
      ],
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
      organizations: [
        { ...owner.organizations[0], current_user_role: "viewer" },
      ],
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
      organizations: [{ ...owner.organizations[0], current_user_role: role }],
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
