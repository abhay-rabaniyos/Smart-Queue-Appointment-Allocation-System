import { useCallback, useEffect, useState } from "react";
import {
  Activity,
  ArrowRight,
  CalendarDays,
  Check,
  Clock3,
  LayoutDashboard,
  LogOut,
  Radio,
  Users,
  Ticket as TicketIcon,
  Waypoints,
} from "lucide-react";
import { api, type Service, type Ticket, type User } from "./api";
import type { Operations } from "./types";
import { status } from "./utils";
import useBoard from "./hooks/useBoard";
import Stat from "./components/Stat";
import RegistrationForm from "./components/RegistrationForm";
import TicketCard from "./components/TicketCard";
import QueueBoard from "./components/QueueBoard";
import AdminTools from "./components/AdminTools";
export default function App() {
  const [view, setView] = useState("visit"),
    [services, setServices] = useState<Service[]>([]),
    [user, setUser] = useState<User | null>(null),
    [error, setError] = useState(""),
    [notice, setNotice] = useState(""),
    [busy, setBusy] = useState(false),
    [ticket, setTicket] = useState<Ticket | null>(null),
    [ops, setOps] = useState<Operations | null>(null);
  const { board, live } = useBoard();
  const refresh = useCallback(async () => {
    if (user) setOps(await api<Operations>("/operations"));
  }, [user]);
  const act = async (fn: () => Promise<unknown>, message = "Saved") => {
    if (busy) return;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await fn();
      setNotice(message);
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong");
    } finally {
      setBusy(false);
    }
  };
  useEffect(() => {
    api<Service[]>("/services")
      .then(setServices)
      .catch(() => setError("Backend unavailable. Start the API and refresh."));
    api<User>("/auth/me")
      .then(setUser)
      .catch(() => {});
    const secret =
      new URLSearchParams(location.hash.slice(1)).get("ticket") ??
      sessionStorage.getItem("qp-ticket");
    if (secret)
      api<Ticket>(`/tickets/${secret}`)
        .then(setTicket)
        .catch(() => {});
  }, []);
  useEffect(() => {
    if (user) {
      void refresh().catch(() => {});
      const timer = setInterval(() => void refresh().catch(() => {}), 5000);
      return () => clearInterval(timer);
    }
  }, [user, refresh]);
  useEffect(() => {
    if (!ticket) return;
    const timer = setInterval(
      () =>
        api<Ticket>(`/tickets/${ticket.secret}`)
          .then(setTicket)
          .catch(() => {}),
      4000,
    );
    return () => clearInterval(timer);
  }, [ticket?.secret]);
  const saveTicket = (value: Ticket) => {
    setTicket(value);
    sessionStorage.setItem("qp-ticket", value.secret);
    history.replaceState(null, "", `#ticket=${value.secret}`);
  };
  const total =
    board?.tickets.filter((t) => t.status === "waiting").length ?? 0;
  return (
    <div className="shell">
      <aside>
        <a className="brand" href="/" aria-label="QueuePilot home">
          <span className="brand-icon">
            <Waypoints size={23} />
          </span>
          QueuePilot<span className="brand-dot">.</span>
        </a>
        <div className="workspace">
          <span className="building">QP</span>
          <div>
            <strong>{board?.organization ?? "Central branch"}</strong>
            <small>SMART SERVICE, EVERY DAY</small>
          </div>
        </div>
        <p className="nav-label">WORKSPACE</p>
        <nav>
          {[
            { id: "visit", label: "Plan your visit", icon: CalendarDays },
            { id: "board", label: "Live queue", icon: Radio },
            { id: "operations", label: "Service desk", icon: LayoutDashboard },
          ].map((item) => (
            <button
              key={item.id}
              className={view === item.id ? "selected" : ""}
              onClick={() => setView(item.id)}
            >
              <item.icon size={19} />
              {item.label}
              {item.id === "board" && (
                <span className="nav-count">{total}</span>
              )}
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="help">
            <Activity size={21} />
            <strong>A little less waiting.</strong>
            <p>Book ahead. Check in. We’ll keep you in the loop.</p>
          </div>
          <small>QUEUEPILOT / AIGNITE 2026</small>
        </div>
      </aside>
      <main>
        <header>
          <div className="breadcrumb">
            Workspace <span>/</span>{" "}
            {view === "visit"
              ? "Plan your visit"
              : view === "board"
                ? "Live queue"
                : "Service desk"}
          </div>
          <div className="header-right">
            <span className={live ? "connection" : "connection offline"}>
              <i />
              {live ? "Live updates" : "Reconnecting"}
            </span>
            <span className="avatar">
              {user ? user.name.slice(0, 2).toUpperCase() : "GU"}
            </span>
          </div>
        </header>
        <div className="content">
          <div className="page-heading">
            <div>
              <p className="eyebrow">A BETTER WAY TO WAIT</p>
              <h1>
                {view === "visit"
                  ? "Your next visit, simplified."
                  : view === "board"
                    ? "Every turn, in real time."
                    : "Keep service moving."}
              </h1>
              <p className="muted">
                {view === "visit"
                  ? "Choose your service. Pick your time. Leave the waiting to us."
                  : view === "board"
                    ? "Follow the queue and see which counters are ready to help."
                    : "One shared view for reception, staff, and administrators."}
              </p>
            </div>
            <span className="date-label">
              {new Date().toLocaleDateString("en-IN", {
                weekday: "short",
                day: "numeric",
                month: "short",
                year: "numeric",
              })}
            </span>
          </div>
          {error && (
            <div role="alert" className="alert error">
              {error}
              <button aria-label="Dismiss error" onClick={() => setError("")}>
                ×
              </button>
            </div>
          )}
          {notice && (
            <div role="status" className="alert success">
              <Check size={18} />
              {notice}
            </div>
          )}
          <section className="stats">
            <Stat
              icon={<Users />}
              label="In the queue"
              value={String(total)}
              note="Across all services"
            />
            <Stat
              icon={<Waypoints />}
              label="Available counters"
              value={String(
                board?.counters.filter((c) => c.active && c.staffed).length ??
                  0,
              )}
              note="Staffed and open"
            />
            <Stat
              icon={<Clock3 />}
              label="Service options"
              value={String(services.length)}
              note="Find the right support"
            />
            <Stat
              icon={<Check />}
              label="Your visit"
              value={ticket ? ticket.token : "Let’s begin"}
              note={ticket ? status(ticket.status) : "Book ahead or walk in"}
            />
          </section>
          {view === "visit" && (
            <div className="visit-grid">
              <section className="panel">
                <div className="panel-heading">
                  <span className="step">01</span>
                  <div>
                    <h2>Make time for what matters</h2>
                    <p>Reserve an appointment or get a walk-in token.</p>
                  </div>
                </div>
                <RegistrationForm
                  services={services}
                  reception={false}
                  busy={busy}
                  onSubmit={(data) =>
                    act(
                      async () =>
                        saveTicket(await api<Ticket>("/tickets", "POST", data)),
                      "Your token is ready",
                    )
                  }
                />
              </section>
              <div className="right-column">
                {ticket ? (
                  <TicketCard
                    ticket={ticket}
                    services={services}
                    counters={board?.counters ?? []}
                    busy={busy}
                    act={act}
                    save={saveTicket}
                  />
                ) : (
                  <section className="ticket-empty">
                    <span className="ticket-symbol">
                      <TicketIcon size={31} />
                    </span>
                    <p className="eyebrow">YOUR PERSONAL QUEUE PASS</p>
                    <h2>
                      A place in line.
                      <br />
                      Peace of mind.
                    </h2>
                    <p>
                      Your token and live status will appear here after you
                      register.
                    </p>
                    <div className="ticket-decoration">
                      · · · · · · · · · · · · · · · · · ·
                    </div>
                    <span>NO PAPER. NO GUESSWORK.</span>
                  </section>
                )}
                <section className="how">
                  <h3>A smoother visit in 3 steps</h3>
                  {[
                    "Choose a service and register",
                    "Check in with your QR queue pass",
                    "Follow your token to the counter",
                  ].map((v, i) => (
                    <div key={v}>
                      <span>{i + 1}</span>
                      <p>{v}</p>
                    </div>
                  ))}
                  <small>
                    Wait times are estimates and may change. Priority is
                    assigned by authorized staff.
                  </small>
                </section>
              </div>
            </div>
          )}
          {view === "board" && <QueueBoard board={board} services={services} />}
          {view === "operations" &&
            (!user ? (
              <section className="panel login">
                <p className="eyebrow">STAFF ACCESS</p>
                <h2>Welcome to your service desk</h2>
                <p className="muted">
                  Sign in with the account configured by your administrator.
                </p>
                <form
                  onSubmit={(e) => {
                    e.preventDefault();
                    const f = new FormData(e.currentTarget);
                    void act(
                      async () =>
                        setUser(
                          await api<User>(
                            "/auth/login",
                            "POST",
                            Object.fromEntries(f),
                          ),
                        ),
                      "Signed in",
                    );
                  }}
                >
                  <label>
                    Email
                    <input
                      name="email"
                      type="email"
                      autoComplete="username"
                      required
                    />
                  </label>
                  <label>
                    Password
                    <input
                      name="password"
                      type="password"
                      autoComplete="current-password"
                      required
                    />
                  </label>
                  <button className="primary" disabled={busy}>
                    Sign in <ArrowRight size={17} />
                  </button>
                </form>
              </section>
            ) : (
              <>
                <div className="operator-heading">
                  <p>
                    Signed in as <strong>{user.name}</strong> · {user.role}
                  </p>
                  <button
                    className="secondary"
                    onClick={() => {
                      setBusy(true);
                      void api("/auth/logout", "POST")
                        .then(() => {
                          setUser(null);
                          setOps(null);
                          setNotice("Signed out");
                        })
                        .catch((e) => setError(e.message))
                        .finally(() => setBusy(false));
                    }}
                  >
                    <LogOut size={16} />
                    Sign out
                  </button>
                </div>
                {ops && (
                  <>
                    <div className="stats compact">
                      <Stat
                        label="Completed"
                        value={String(ops.analytics.completed)}
                        note="Latest 500 registrations"
                      />
                      <Stat
                        label="Average wait"
                        value={`${ops.analytics.average_wait} min`}
                        note="Completed visits only"
                      />
                      <Stat
                        label="No-shows"
                        value={String(ops.analytics.no_shows)}
                        note="Processed by worker"
                      />
                    </div>
                    {user.role !== "staff" && (
                      <section className="panel">
                        <h2>Reception registration</h2>
                        <RegistrationForm
                          services={services}
                          reception
                          busy={busy}
                          onSubmit={(data) =>
                            act(
                              async () =>
                                saveTicket(
                                  await api<Ticket>(
                                    "/reception/tickets",
                                    "POST",
                                    data,
                                  ),
                                ),
                              "Visitor registered",
                            )
                          }
                        />
                        {ticket && (
                          <p className="muted">
                            Latest token: <strong>{ticket.token}</strong> ·{" "}
                            <a
                              href={`/#ticket=${ticket.secret}`}
                              onClick={() => setView("visit")}
                            >
                              View queue pass
                            </a>
                          </p>
                        )}
                      </section>
                    )}
                    <section className="panel">
                      <div className="section-title">
                        <h2>Counter workspace</h2>
                        {user.role === "admin" && (
                          <button
                            className="secondary"
                            disabled={busy}
                            onClick={() =>
                              void act(
                                () => api("/admin/dispatch", "POST"),
                                "Available counters allocated",
                              )
                            }
                          >
                            Allocate available counters
                          </button>
                        )}
                        <span className="muted">
                          Call next uses priority + waiting time
                        </span>
                      </div>
                      <div className="counter-grid">
                        {ops.counters
                          .filter(
                            (c) =>
                              user.role === "admin" || c.staff_id === user.id,
                          )
                          .map((c) => {
                            const serving = ops.tickets.find(
                              (t) =>
                                t.counter_id === c.id && t.status === "serving",
                            );
                            return (
                              <article className="counter-card" key={c.id}>
                                <div className="section-title">
                                  <h3>{c.name}</h3>
                                  <span
                                    className={`badge ${c.active ? "waiting" : "cancelled"}`}
                                  >
                                    {c.active ? "Open" : "Paused"}
                                  </span>
                                </div>
                                <p>
                                  {
                                    services.find((s) => s.id === c.service_id)
                                      ?.name
                                  }
                                </p>
                                <strong className="counter-token">
                                  {serving?.token ?? "Ready for next"}
                                </strong>
                                {serving && <p>{serving.name}</p>}
                                <button
                                  className="primary"
                                  disabled={busy || !c.active || !c.staff_id}
                                  onClick={() =>
                                    void act(
                                      () =>
                                        api(
                                          `/counters/${c.id}/${serving ? "complete" : "call"}`,
                                          "POST",
                                        ),
                                      serving
                                        ? "Visit completed"
                                        : "Customer called",
                                    )
                                  }
                                >
                                  {serving ? "Complete visit" : "Call next"}
                                  <ArrowRight size={16} />
                                </button>
                              </article>
                            );
                          })}
                      </div>
                    </section>
                    <section className="panel">
                      <h2>Appointments & visitors</h2>
                      <div className="table-wrap">
                        <table>
                          <thead>
                            <tr>
                              <th>Token / Visitor</th>
                              <th>Appointment</th>
                              <th>Status</th>
                              <th>Priority</th>
                              <th>Actions</th>
                            </tr>
                          </thead>
                          <tbody>
                            {ops.tickets.map((t) => (
                              <tr key={t.id}>
                                <td>
                                  <strong>{t.token}</strong>
                                  <small>{t.name}</small>
                                </td>
                                <td>
                                  {t.slot
                                    ? new Date(t.slot).toLocaleString()
                                    : "Walk-in"}
                                </td>
                                <td>
                                  <span className={`badge ${t.status}`}>
                                    {status(t.status)}
                                  </span>
                                </td>
                                <td>
                                  {
                                    ["Standard", "Priority", "Urgent"][
                                      t.priority
                                    ]
                                  }
                                </td>
                                <td>
                                  {["booked", "waiting"].includes(t.status) && (
                                    <button
                                      className="text-button"
                                      onClick={() => {
                                        saveTicket(t);
                                        setView("visit");
                                      }}
                                    >
                                      Manage
                                    </button>
                                  )}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                        {!ops.tickets.length && (
                          <p className="empty">No visitors registered yet.</p>
                        )}
                      </div>
                    </section>
                    {user.role === "admin" && (
                      <AdminTools
                        ops={ops}
                        busy={busy}
                        act={act}
                        reloadServices={() =>
                          api<Service[]>("/services").then(setServices)
                        }
                      />
                    )}
                  </>
                )}
              </>
            ))}
          <footer>
            <span>
              <Waypoints size={15} /> QueuePilot
            </span>
            <p>More clarity. Less waiting.</p>
            <small>Appointments · Walk-ins · One queue</small>
          </footer>
        </div>
      </main>
    </div>
  );
}
