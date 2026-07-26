import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { describe, expect, it, vi } from "vitest";
import { App } from "../App";
import { AuthProvider } from "../auth/AuthProvider";
import type { Me, NotificationEvent, Page } from "../types";

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

const viewer: Me = {
  user: {
    id: "u2",
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

function pendingEvent(
  overrides: Partial<NotificationEvent> = {},
): NotificationEvent {
  return {
    id: "n1",
    organization_id: "o1",
    source_event_type: "security.finding.created",
    source_resource_type: "finding",
    source_resource_id: "f1",
    channel: "email",
    template_key: "critical_finding_created",
    destination_reference: null,
    status: "pending_approval",
    attempt_count: 0,
    approved_by_user_id: null,
    approved_at: null,
    scheduled_at: null,
    delivered_at: null,
    failed_at: null,
    failure_reason: null,
    provider_key: null,
    provider_message_id: null,
    created_at: "2026-07-25T00:00:00Z",
    updated_at: "2026-07-25T00:00:00Z",
    ...overrides,
  };
}

function renderNotifications(me: Me, fetchImpl: typeof fetch) {
  vi.stubGlobal("fetch", fetchImpl);
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={["/notifications"]}>
        <AuthProvider initialMe={me} restoreOnMount={false}>
          <App />
        </AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("Notifications page", () => {
  it("lists a pending-approval notification and lets an owner approve it", async () => {
    let approved = false;
    const fetchMock = vi.fn(
      async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        if (url.includes("/notifications/n1/approve")) {
          approved = true;
          return new Response(
            JSON.stringify(
              pendingEvent({
                status: "approved",
                approved_at: "2026-07-25T01:00:00Z",
                approved_by_user_id: "u1",
              }),
            ),
            { status: 200, headers: { "Content-Type": "application/json" } },
          );
        }
        if (url.includes("/api/v1/notifications?")) {
          const body: Page<NotificationEvent> = {
            items: [
              approved ? pendingEvent({ status: "approved" }) : pendingEvent(),
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
    renderNotifications(owner, fetchMock);

    expect(
      await screen.findByRole("heading", { name: "Notifications" }),
    ).toBeInTheDocument();
    expect(
      await screen.findByText("critical_finding_created"),
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
      expect.stringContaining("/api/v1/notifications/n1/approve"),
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("does not show approve or deliver controls for a viewer", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/api/v1/notifications?")) {
        const body: Page<NotificationEvent> = {
          items: [pendingEvent()],
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
    renderNotifications(viewer, fetchMock);

    expect(
      await screen.findByText("critical_finding_created"),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Approve" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Deliver" }),
    ).not.toBeInTheDocument();
  });

  it("shows an empty state when no notifications exist", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/api/v1/notifications?")) {
        const body: Page<NotificationEvent> = {
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
    renderNotifications(owner, fetchMock);

    expect(await screen.findByText("No notifications.")).toBeInTheDocument();
  });

  it("shows an API error state without crashing the page", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/api/v1/notifications?")) {
        return new Response(
          JSON.stringify({ error: { code: "server_error", message: "boom" } }),
          { status: 500, headers: { "Content-Type": "application/json" } },
        );
      }
      return new Response(JSON.stringify([]), { status: 200 });
    });
    renderNotifications(owner, fetchMock);

    expect(
      await screen.findByRole("heading", { name: "Notifications" }),
    ).toBeInTheDocument();
    expect(
      await screen.findByText("Unable to load notifications."),
    ).toBeInTheDocument();
  });

  it("surfaces a failed approval action without crashing the page", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/notifications/n1/approve")) {
        return new Response(
          JSON.stringify({
            error: {
              code: "notification_event_invalid_transition",
              message:
                "Cannot approve a notification event in status 'delivered'.",
            },
          }),
          { status: 409, headers: { "Content-Type": "application/json" } },
        );
      }
      if (url.includes("/api/v1/notifications?")) {
        const body: Page<NotificationEvent> = {
          items: [pendingEvent()],
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
    renderNotifications(owner, fetchMock);

    const approveButton = await screen.findByRole("button", {
      name: "Approve",
    });
    await userEvent.click(approveButton);

    expect(
      await screen.findByText(
        "Cannot approve a notification event in status 'delivered'.",
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Notifications" }),
    ).toBeInTheDocument();
  });

  it("filters notifications by status", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/api/v1/notifications?")) {
        const body: Page<NotificationEvent> = {
          items: url.includes("status=delivered")
            ? [
                pendingEvent({
                  id: "n2",
                  status: "delivered",
                  attempt_count: 1,
                }),
              ]
            : [pendingEvent()],
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
    renderNotifications(owner, fetchMock);

    await screen.findByText("critical_finding_created");
    const select = screen.getByLabelText("Status");
    await userEvent.selectOptions(select, "delivered");

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining("status=delivered"),
        expect.anything(),
      ),
    );
  });

  it("shows a delivered notification without action controls", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/api/v1/notifications?")) {
        const body: Page<NotificationEvent> = {
          items: [
            pendingEvent({
              status: "delivered",
              attempt_count: 1,
              approved_at: "2026-07-25T01:00:00Z",
              delivered_at: "2026-07-25T01:05:00Z",
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
    renderNotifications(owner, fetchMock);

    expect(
      await screen.findByText("critical_finding_created"),
    ).toBeInTheDocument();
    expect(
      within(screen.getByRole("table")).getByText("Delivered"),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Approve" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Deliver" }),
    ).not.toBeInTheDocument();
  });
});
