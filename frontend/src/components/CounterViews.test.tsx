import { beforeEach, describe, it, expect, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { CounterSummary, Ticket } from "../api";
import CounterOverview from "./CounterOverview";
import TicketCard from "./TicketCard";
import App from "../App";

const counters: CounterSummary[] = [
  {
    id: "c1",
    name: "Counter 01",
    service_id: "svc",
    service_name: "Consultation",
    active: true,
    staffed: true,
    service_active: true,
    availability: "serving",
    serving_token: "A-0001",
    waiting_count: 4,
  },
  {
    id: "c2",
    name: "Counter 02",
    service_id: "svc",
    service_name: "Consultation",
    active: true,
    staffed: true,
    service_active: true,
    availability: "available",
    serving_token: null,
    waiting_count: 4,
  },
  {
    id: "c3",
    name: "Bank desk",
    service_id: "bank",
    service_name: "Banking",
    active: false,
    staffed: false,
    service_active: true,
    availability: "paused",
    serving_token: null,
    waiting_count: 0,
  },
];
const staff = [
  { id: "u1", name: "First Staff", role: "staff" as const, active: true },
  { id: "u2", name: "Second Staff", role: "staff" as const, active: true },
];
const assignments = counters.map((c, i) => ({
  ...c,
  staff_id: staff[i]?.id ?? null,
}));
const ticket: Ticket = {
  id: "t1",
  secret: "test-secret",
  token: "W-0002",
  name: "Test Visitor",
  service_id: "svc",
  status: "waiting",
  slot: null,
  counter_id: null,
  priority: 0,
  position: 1,
  eta_minutes: 0,
};
beforeEach(() => {
  sessionStorage.clear();
  history.replaceState(null, "", "/");
});

describe("counter context", () => {
  it("distinguishes shared queues and current tokens and filters other services", async () => {
    render(<CounterOverview counters={counters} />);
    expect(
      within(
        screen.getByRole("article", { name: "Counter 01 details" }),
      ).getByText("A-0001"),
    ).toBeInTheDocument();
    expect(screen.getAllByText("4 waiting")).toHaveLength(2);
    expect(screen.queryByText("First Staff")).not.toBeInTheDocument();
    await userEvent.selectOptions(
      screen.getByLabelText("Filter counter services"),
      "bank",
    );
    expect(
      screen.getByRole("article", { name: "Bank desk details" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("article", { name: "Counter 01 details" }),
    ).not.toBeInTheDocument();
  });
  it("shows staff assignments and highlights only the signed-in staff counter", () => {
    render(
      <CounterOverview
        counters={counters}
        assignments={assignments}
        staff={staff}
        user={staff[0]}
      />,
    );
    expect(
      within(
        screen.getByRole("article", { name: "Counter 01 details" }),
      ).getByText("Your counter"),
    ).toBeInTheDocument();
    expect(screen.getByText("Second Staff · staff")).toBeInTheDocument();
  });
  it("keeps waiting tickets unassigned and names the counter only after allocation", () => {
    const props = {
      services: [],
      counters,
      busy: false,
      act: vi.fn(),
      save: vi.fn(),
    };
    const { rerender } = render(<TicketCard {...props} ticket={ticket} />);
    expect(
      screen.getByText(/Your counter will be assigned when called/),
    ).toBeInTheDocument();
    expect(screen.queryByText(/Please proceed/)).not.toBeInTheDocument();
    rerender(
      <TicketCard
        {...props}
        ticket={{ ...ticket, status: "serving", counter_id: "c2" }}
      />,
    );
    expect(
      screen.getByText(/Please proceed to Counter 02/),
    ).toBeInTheDocument();
  });
  it.each(["admin", "receptionist", "staff"] as const)(
    "shows counter context with correct actions for %s",
    async (role) => {
      const user = {
        id: role === "staff" ? "u1" : "operator",
        name: "Operator",
        role,
      };
      const services = [
        {
          id: "svc",
          name: "Consultation",
          minutes: 10,
          capacity: 2,
          active: true,
        },
      ];
      vi.stubGlobal(
        "WebSocket",
        class {
          close() {}
        },
      );
      vi.stubGlobal(
        "fetch",
        vi.fn(async (input: string) => {
          const path = String(input);
          const data =
            path === "/api/auth/me"
              ? user
              : path === "/api/services"
                ? services
                : path === "/api/board"
                  ? { organization: "Branch", counters, tickets: [] }
                  : path === "/api/operations"
                    ? {
                        tickets: [
                          ticket,
                          {
                            ...ticket,
                            id: "assigned",
                            token: "A-0001",
                            status: "serving",
                            counter_id: "c1",
                          },
                          {
                            ...ticket,
                            id: "bank-ticket",
                            token: "B-0003",
                            service_id: "bank",
                            status: "booked",
                          },
                        ],
                        counters: assignments,
                        counter_summaries: counters,
                        services,
                        staff,
                        rules: {
                          aging_minutes: 15,
                          priority_weight: 30,
                          grace_minutes: 15,
                        },
                        analytics: {
                          completed: 0,
                          average_wait: 0,
                          waiting: 0,
                          no_shows: 0,
                          sample_limit: 500,
                        },
                        outbox: [],
                        audit: [],
                      }
                    : [];
          return new Response(JSON.stringify(data), { status: 200 });
        }),
      );
      render(<App />);
      await userEvent.click(
        screen.getByRole("button", { name: "Service desk" }),
      );
      await screen.findByRole("heading", { name: "Counter workspace" });
      const first = screen.getByRole("article", { name: "Counter 01 details" });
      const second = screen.getByRole("article", {
        name: "Counter 02 details",
      });
      expect(within(first).getByText("A-0001")).toBeInTheDocument();
      expect(
        within(first).queryByRole("button", { name: "Complete visit" }) !==
          null,
      ).toBe(role !== "receptionist");
      expect(
        within(second).queryByRole("button", { name: "Call next" }) !== null,
      ).toBe(role === "admin");
      await userEvent.selectOptions(
        screen.getByLabelText("Filter visitors by counter"),
        "c2",
      );
      const table = screen.getByRole("table", {
        name: "Appointments and visitors",
      });
      expect(within(table).getByText("W-0002")).toBeInTheDocument();
      expect(within(table).queryByText("A-0001")).not.toBeInTheDocument();
      expect(within(table).queryByText("B-0003")).not.toBeInTheDocument();
      expect(within(table).getByText("Consultation")).toBeInTheDocument();
      await userEvent.selectOptions(
        screen.getByLabelText("Filter visitors by service"),
        "svc",
      );
      await userEvent.selectOptions(
        screen.getByLabelText("Filter visitors by counter"),
        "c3",
      );
      expect(
        screen.getByText("No visitors match the selected service and counter."),
      ).toBeInTheDocument();
    },
  );
  it("keeps the requested service visible when the service is no longer bookable", () => {
    render(
      <TicketCard
        ticket={{
          ...ticket,
          status: "completed",
          service_name: "Archived consultation",
        }}
        services={[]}
        counters={[]}
        busy={false}
        act={vi.fn()}
        save={vi.fn()}
      />,
    );
    expect(
      screen.getByRole("heading", { name: "Archived consultation" }),
    ).toBeInTheDocument();
  });
});
