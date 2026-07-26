import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { describe, expect, it, vi } from "vitest";
import { App } from "../App";
import { AuthProvider } from "../auth/AuthProvider";
import type { Me, Page, ScanRun, ScanSchedule } from "../types";

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

function schedule(overrides: Partial<ScanSchedule> = {}): ScanSchedule {
  return {
    id: "s1",
    organization_id: "o1",
    aws_account_id: "a1",
    name: "Nightly scan",
    interval_minutes: 60,
    enabled: true,
    created_by_user_id: "u1",
    last_run_at: null,
    next_run_at: "2026-07-26T00:00:00Z",
    created_at: "2026-07-25T00:00:00Z",
    updated_at: "2026-07-25T00:00:00Z",
    ...overrides,
  };
}

function emptyRuns(): Page<ScanRun> {
  return { items: [], total: 0, page: 1, page_size: 10 };
}

function renderSchedules(me: Me, fetchImpl: typeof fetch) {
  vi.stubGlobal("fetch", fetchImpl);
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={["/schedules"]}>
        <AuthProvider initialMe={me} restoreOnMount={false}>
          <App />
        </AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("Schedules page", () => {
  it("lists a schedule and lets an owner disable it", async () => {
    let enabled = true;
    const fetchMock = vi.fn(
      async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        if (url.includes("/schedules/s1/disable")) {
          enabled = false;
          return new Response(JSON.stringify(schedule({ enabled: false })), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          });
        }
        if (url.includes("/api/v1/schedules?")) {
          const body: Page<ScanSchedule> = {
            items: [schedule({ enabled })],
            total: 1,
            page: 1,
            page_size: 10,
          };
          return new Response(JSON.stringify(body), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          });
        }
        if (url.includes("/api/v1/scan-runs?")) {
          return new Response(JSON.stringify(emptyRuns()), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          });
        }
        if (url.includes("/api/v1/aws/accounts?")) {
          return new Response(JSON.stringify([]), { status: 200 });
        }
        void init;
        return new Response(JSON.stringify([]), { status: 200 });
      },
    );
    renderSchedules(owner, fetchMock);

    expect(
      await screen.findByRole("heading", { name: "Scheduled scans" }),
    ).toBeInTheDocument();
    expect(await screen.findByText("Nightly scan")).toBeInTheDocument();
    expect(screen.getByText("Enabled")).toBeInTheDocument();

    const disableButton = await screen.findByRole("button", {
      name: "Disable",
    });
    await userEvent.click(disableButton);

    await waitFor(() => expect(enabled).toBe(false));
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/api/v1/schedules/s1/disable"),
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("does not show the create form or management actions for a viewer", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/api/v1/schedules?")) {
        const body: Page<ScanSchedule> = {
          items: [schedule()],
          total: 1,
          page: 1,
          page_size: 10,
        };
        return new Response(JSON.stringify(body), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }
      if (url.includes("/api/v1/scan-runs?")) {
        return new Response(JSON.stringify(emptyRuns()), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }
      return new Response(JSON.stringify([]), { status: 200 });
    });
    renderSchedules(viewer, fetchMock);

    expect(await screen.findByText("Nightly scan")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Create schedule" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Disable" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Run now" }),
    ).not.toBeInTheDocument();
  });

  it("shows an empty state when there are no schedules", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/api/v1/schedules?")) {
        return new Response(
          JSON.stringify({ items: [], total: 0, page: 1, page_size: 10 }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }
      if (url.includes("/api/v1/scan-runs?")) {
        return new Response(JSON.stringify(emptyRuns()), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }
      return new Response(JSON.stringify([]), { status: 200 });
    });
    renderSchedules(owner, fetchMock);

    expect(await screen.findByText("No schedules yet.")).toBeInTheDocument();
    expect(await screen.findByText("No scan runs yet.")).toBeInTheDocument();
  });

  it("surfaces a failed run-now action without crashing the page", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/schedules/s1/run")) {
        return new Response(
          JSON.stringify({
            error: {
              code: "schedule_disabled",
              message: "This schedule is disabled.",
            },
          }),
          { status: 409, headers: { "Content-Type": "application/json" } },
        );
      }
      if (url.includes("/api/v1/schedules?")) {
        const body: Page<ScanSchedule> = {
          items: [schedule()],
          total: 1,
          page: 1,
          page_size: 10,
        };
        return new Response(JSON.stringify(body), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }
      if (url.includes("/api/v1/scan-runs?")) {
        return new Response(JSON.stringify(emptyRuns()), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }
      return new Response(JSON.stringify([]), { status: 200 });
    });
    renderSchedules(owner, fetchMock);

    const runButton = await screen.findByRole("button", { name: "Run now" });
    await userEvent.click(runButton);

    expect(
      await screen.findByText("This schedule is disabled."),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Scheduled scans" }),
    ).toBeInTheDocument();
  });

  it("lists recent scan runs with their status", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/api/v1/schedules?")) {
        const body: Page<ScanSchedule> = {
          items: [schedule()],
          total: 1,
          page: 1,
          page_size: 10,
        };
        return new Response(JSON.stringify(body), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }
      if (url.includes("/api/v1/scan-runs?")) {
        const body: Page<ScanRun> = {
          items: [
            {
              id: "r1",
              organization_id: "o1",
              aws_account_id: "a1",
              schedule_id: "s1",
              trigger: "scheduled",
              status: "failed",
              discovery_job_id: null,
              evaluation_job_id: null,
              error_summary: "aws_account_not_connected",
              started_at: "2026-07-25T00:00:00Z",
              finished_at: "2026-07-25T00:05:00Z",
              created_at: "2026-07-25T00:00:00Z",
              updated_at: "2026-07-25T00:05:00Z",
            },
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
    renderSchedules(owner, fetchMock);

    expect(
      await screen.findByText("aws_account_not_connected"),
    ).toBeInTheDocument();
    expect(screen.getByText("scheduled")).toBeInTheDocument();
  });
});
