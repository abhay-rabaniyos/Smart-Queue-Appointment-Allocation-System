import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import App from "./App";
const service = {
  id: "svc",
  name: "General consultation",
  minutes: 10,
  capacity: 2,
  active: true,
};
const ticket = {
  id: "t1",
  secret: "private-pass",
  token: "W-0001",
  name: "Alex Thomas",
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
  vi.stubGlobal(
    "WebSocket",
    class {
      close() {}
    },
  );
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: string, init?: RequestInit) => {
      const path = String(input);
      let body: unknown = {};
      let code = 200;
      if (path === "/api/services") body = [service];
      else if (path === "/api/auth/me") {
        body = { detail: "Sign in required" };
        code = 401;
      } else if (path === "/api/board")
        body = { organization: "Central branch", tickets: [], counters: [] };
      else if (path.includes("/slots"))
        body = [{ time: "2026-11-18T04:00:00Z", remaining: 2 }];
      else if (path === "/api/tickets" && init?.method === "POST")
        body = ticket;
      return new Response(JSON.stringify(body), {
        status: code,
        headers: { "Content-Type": "application/json" },
      });
    }),
  );
});
describe("customer experience", () => {
  it("registers a walk-in and displays a private queue pass", async () => {
    const user = userEvent.setup();
    render(<App />);
    await screen.findByRole("option", { name: /General consultation/ });
    await user.click(screen.getByRole("button", { name: "Walk in" }));
    await user.type(screen.getByLabelText("Full name"), "Alex Thomas");
    await user.click(screen.getByRole("button", { name: "Get walk-in token" }));
    await screen.findByRole("heading", { name: "General consultation" });
    expect(sessionStorage.getItem("qp-ticket")).toBe("private-pass");
    expect(screen.getByAltText(/QR queue pass/)).toHaveAttribute(
      "src",
      "/api/tickets/private-pass/qr",
    );
    const call = vi
      .mocked(fetch)
      .mock.calls.find(
        ([url, init]) => url === "/api/tickets" && init?.method === "POST",
      );
    expect(JSON.parse(call![1]!.body as string)).toMatchObject({
      name: "Alex Thomas",
      source: "walk_in",
      priority: 0,
      slot: null,
    });
  });
  it("requires a time selection before appointment submission", async () => {
    render(<App />);
    await screen.findByRole("option", { name: /General consultation/ });
    expect(
      screen.getByRole("button", { name: "Confirm appointment" }),
    ).toBeDisabled();
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /left/ })).toBeInTheDocument(),
    );
  });
  it("renders staff login when signed out", async () => {
    const user = userEvent.setup();
    render(<App />);
    await user.click(screen.getByRole("button", { name: "Service desk" }));
    expect(screen.getByLabelText("Password")).toHaveAttribute(
      "type",
      "password",
    );
    expect(screen.getByRole("button", { name: "Sign in" })).toBeInTheDocument();
  });
  it("shows safe empty states on the queue board", async () => {
    const user = userEvent.setup();
    render(<App />);
    await user.click(screen.getByRole("button", { name: /Live queue/ }));
    expect(
      screen.getByText("A clear queue. You’re right on time."),
    ).toBeInTheDocument();
  });
  it("displays server validation errors", async () => {
    const original = vi.mocked(fetch).getMockImplementation()!;
    vi.mocked(fetch).mockImplementation(async (input, init) =>
      input === "/api/tickets"
        ? new Response(JSON.stringify({ detail: "Service unavailable" }), {
            status: 409,
          })
        : original(input, init),
    );
    const user = userEvent.setup();
    render(<App />);
    await screen.findByRole("option", { name: /General consultation/ });
    await user.click(screen.getByRole("button", { name: "Walk in" }));
    await user.type(screen.getByLabelText("Full name"), "Alex Thomas");
    await user.click(screen.getByRole("button", { name: "Get walk-in token" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Service unavailable",
    );
  });
});
