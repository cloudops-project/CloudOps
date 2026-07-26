import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { describe, expect, it, vi } from "vitest";
import { App } from "../App";
import { AuthProvider } from "../auth/AuthProvider";
import type { AuditEvent, Me, Page } from "../types";

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

function event(overrides: Partial<AuditEvent> = {}): AuditEvent {
  return {
    id: "e1",
    organization_id: "o1",
    actor_user_id: "u1",
    event_type: "scheduler.schedule.created",
    resource_type: "scan_schedule",
    resource_id: "s1",
    result: "succeeded",
    created_at: "2026-07-25T00:00:00Z",
    ...overrides,
  };
}

function renderAudit(me: Me, fetchImpl: typeof fetch) {
  vi.stubGlobal("fetch", fetchImpl);
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={["/audit"]}>
        <AuthProvider initialMe={me} restoreOnMount={false}>
          <App />
        </AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("Audit page", () => {
  it("lists audit events for an owner", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/api/v1/audit-events?")) {
        const body: Page<AuditEvent> = {
          items: [event()],
          total: 1,
          page: 1,
          page_size: 25,
        };
        return new Response(JSON.stringify(body), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }
      return new Response(JSON.stringify([]), { status: 200 });
    });
    renderAudit(owner, fetchMock);

    expect(
      await screen.findByRole("heading", { name: "Audit log" }),
    ).toBeInTheDocument();
    expect(
      await screen.findByText("scheduler.schedule.created"),
    ).toBeInTheDocument();
  });

  it("shows an access message instead of calling the API for a role without audit read", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      void input;
      return new Response(JSON.stringify([]), { status: 200 });
    });
    renderAudit(cloudEngineer, fetchMock);

    expect(
      await screen.findByText(
        "You do not have access to the audit log for this organization.",
      ),
    ).toBeInTheDocument();
    expect(
      fetchMock.mock.calls.some(([input]) =>
        String(input).includes("/audit-events"),
      ),
    ).toBe(false);
  });

  it("shows an empty state when no events match the filters", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/api/v1/audit-events?")) {
        return new Response(
          JSON.stringify({ items: [], total: 0, page: 1, page_size: 25 }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }
      return new Response(JSON.stringify([]), { status: 200 });
    });
    renderAudit(owner, fetchMock);

    expect(
      await screen.findByText("No audit events match these filters."),
    ).toBeInTheDocument();
  });

  it("filters by event type", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/api/v1/audit-events?")) {
        const body: Page<AuditEvent> = {
          items: url.includes("event_type=scheduler.run.failed")
            ? [
                event({
                  id: "e2",
                  event_type: "scheduler.run.failed",
                  result: "failed",
                }),
              ]
            : [event()],
          total: 1,
          page: 1,
          page_size: 25,
        };
        return new Response(JSON.stringify(body), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }
      return new Response(JSON.stringify([]), { status: 200 });
    });
    renderAudit(owner, fetchMock);

    await screen.findByText("scheduler.schedule.created");
    const input = screen.getByLabelText("Event type");
    await userEvent.type(input, "scheduler.run.failed");

    expect(await screen.findByText("scheduler.run.failed")).toBeInTheDocument();
  });
});
