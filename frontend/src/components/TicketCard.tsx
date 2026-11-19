import { useEffect, useState } from "react";
import { Ticket as TicketIcon } from "lucide-react";
import { api, type Ticket, type Service, type CounterSummary } from "../api";
import { counterStatus } from "./CounterOverview";
import { today, formatTime, status } from "../utils";
export default function TicketCard({
  ticket,
  services,
  counters,
  busy,
  act,
  save,
}: {
  ticket: Ticket;
  services: Service[];
  counters: CounterSummary[];
  busy: boolean;
  act: (fn: () => Promise<unknown>, message?: string) => Promise<void>;
  save: (t: Ticket) => void;
}) {
  const [rescheduling, setRescheduling] = useState(false),
    [newSlot, setNewSlot] = useState(""),
    [day, setDay] = useState(today()),
    [slots, setSlots] = useState<{ time: string; remaining: number }[]>([]);
  useEffect(() => {
    let current = true;
    if (rescheduling)
      api<typeof slots>(`/services/${ticket.service_id}/slots?day=${day}`)
        .then((v) => {
          if (current) setSlots(v);
        })
        .catch(() => {
          if (current) setSlots([]);
        });
    return () => {
      current = false;
    };
  }, [rescheduling, day, ticket.service_id]);
  const command = (action: string, body?: unknown) =>
    act(
      async () => {
        save(
          await api<Ticket>(
            `/tickets/${ticket.secret}/${action}`,
            "POST",
            body,
          ),
        );
        if (action === "reschedule") setRescheduling(false);
      },
      action === "check-in" ? "You’re checked in" : "Visit updated",
    );
  const serviceName =
    ticket.service_name ||
    services.find((s) => s.id === ticket.service_id)?.name ||
    counters.find((c) => c.service_id === ticket.service_id)?.service_name ||
    "Service unavailable";
  return (
    <section className="queue-pass">
      <div className="section-title">
        <span>
          <TicketIcon size={17} /> YOUR QUEUE PASS
        </span>
        <span className={`badge ${ticket.status}`}>
          {status(ticket.status)}
        </span>
      </div>
      <strong className="big-token">{ticket.token}</strong>
      <small className="qr-note">SERVICE</small>
      <h3>{serviceName}</h3>
      <p>{ticket.name}</p>
      {ticket.slot && <p>{new Date(ticket.slot).toLocaleString()}</p>}
      <div className="ticket-counter-info">
        <strong>
          {ticket.counter_id ? "Assigned counter" : "Counter assignment"}
        </strong>
        {ticket.counter_id ? (
          <p>
            {counters.find((c) => c.id === ticket.counter_id)?.name ??
              "Counter details unavailable"}
          </p>
        ) : ["booked", "waiting"].includes(ticket.status) ? (
          <>
            <p>
              {ticket.status === "booked"
                ? "Check in near your appointment time. Your counter will be assigned when called."
                : "You are in the shared service queue. Your counter will be assigned when called."}
            </p>
            <ul>
              {counters
                .filter((c) => c.service_id === ticket.service_id)
                .map((c) => (
                  <li key={c.id}>
                    <span>
                      {c.name} · {c.service_name}
                    </span>
                    <small>{counterStatus[c.availability]}</small>
                  </li>
                ))}
            </ul>
            {!counters.some(
              (c) =>
                c.service_id === ticket.service_id &&
                ["available", "serving"].includes(c.availability),
            ) && (
              <p>
                No staffed, open counter is currently available for this
                service.
              </p>
            )}
          </>
        ) : (
          <p>No counter was assigned.</p>
        )}
      </div>
      <div className="pass-metrics">
        <div>
          <small>QUEUE POSITION</small>
          <strong>{ticket.position ?? "—"}</strong>
        </div>
        <div>
          <small>ESTIMATED WAIT</small>
          <strong>
            {ticket.eta_minutes === null ? "—" : `${ticket.eta_minutes} min`}
          </strong>
        </div>
      </div>
      {ticket.status === "serving" && (
        <div className="callout">
          Please proceed to{" "}
          {counters.find((c) => c.id === ticket.counter_id)?.name ??
            "your assigned counter"}{" "}
          for {serviceName}.
        </div>
      )}
      <img
        className="qr"
        src={`/api/tickets/${ticket.secret}/qr`}
        alt="QR queue pass: scan to open your ticket and check in"
      />
      <small className="qr-note">
        Keep this pass private. Scan to open and check in.
      </small>
      <div className="pass-actions">
        {ticket.status === "booked" && (
          <>
            <button
              className="primary"
              disabled={busy}
              onClick={() => void command("check-in")}
            >
              Check in
            </button>
            <button
              className="secondary"
              onClick={() => setRescheduling(!rescheduling)}
            >
              Reschedule
            </button>
          </>
        )}
        {["booked", "waiting"].includes(ticket.status) && (
          <button
            className="text-button danger"
            disabled={busy}
            onClick={() => {
              if (window.confirm("Cancel this visit?")) void command("cancel");
            }}
          >
            Cancel visit
          </button>
        )}
      </div>
      {rescheduling && ticket.status === "booked" && (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void command("reschedule", { slot: newSlot });
          }}
        >
          <label>
            New date
            <input
              type="date"
              min={today()}
              value={day}
              onChange={(e) => {
                setDay(e.target.value);
                setNewSlot("");
              }}
            />
          </label>
          <label>
            New time
            <select
              value={newSlot}
              onChange={(e) => setNewSlot(e.target.value)}
              required
            >
              <option value="">Choose a time</option>
              {slots
                .filter((s) => s.remaining > 0)
                .map((s) => (
                  <option key={s.time} value={s.time}>
                    {formatTime(s.time)}
                  </option>
                ))}
            </select>
          </label>
          <button className="primary" disabled={busy || !newSlot}>
            Save appointment
          </button>
        </form>
      )}
    </section>
  );
}
