import { useState, type ReactNode } from "react";
import type { Counter, CounterSummary, User } from "../api";

export const counterStatus = {
  available: "Ready for next",
  serving: "Serving",
  paused: "Paused",
  unstaffed: "No active staff",
  service_unavailable: "Service unavailable",
};
export default function CounterOverview({
  counters,
  staff,
  assignments,
  user,
  renderActions,
  title = "Counter directory",
}: {
  counters: CounterSummary[];
  staff?: (User & { active: boolean })[];
  assignments?: Counter[];
  user?: User;
  renderActions?: (counter: CounterSummary) => ReactNode;
  title?: string;
}) {
  const [service, setService] = useState("all");
  const services = new Map(counters.map((c) => [c.service_id, c.service_name]));
  const visible = counters.filter(
    (c) => service === "all" || c.service_id === service,
  );
  return (
    <section className="panel counter-overview">
      <div className="section-title">
        <h2>{title}</h2>
        <label>
          Filter counter services
          <select value={service} onChange={(e) => setService(e.target.value)}>
            <option value="all">All services</option>
            {[...services].map(([id, name]) => (
              <option key={id} value={id}>
                {name}
              </option>
            ))}
          </select>
        </label>
      </div>
      <p className="muted">
        Counters handling the same service share one waiting queue. A counter is
        assigned when a visitor is called; positions are within the service
        queue.
      </p>
      <div className="counter-grid">
        {visible.map((c) => {
          const assignment = assignments?.find((a) => a.id === c.id);
          const member = staff?.find((s) => s.id === assignment?.staff_id);
          const mine = Boolean(user && assignment?.staff_id === user.id);
          return (
            <article
              className={`counter-card ${mine ? "my-counter" : ""}`}
              key={c.id}
              aria-label={`${c.name} details`}
            >
              <div className="section-title">
                <h3>{c.name}</h3>
                {mine && <span className="badge waiting">Your counter</span>}
              </div>
              <span
                className={`badge ${c.availability === "serving" ? "serving" : c.availability === "available" ? "waiting" : "cancelled"}`}
              >
                {counterStatus[c.availability]}
              </span>
              <dl className="counter-details">
                <div>
                  <dt>Service</dt>
                  <dd>{c.service_name}</dd>
                </div>
                {staff && (
                  <div>
                    <dt>Assigned staff</dt>
                    <dd>
                      {member
                        ? `${member.name} · ${member.role}${member.active ? "" : " (disabled)"}`
                        : "Unassigned"}
                    </dd>
                  </div>
                )}
                <div>
                  <dt>Now serving</dt>
                  <dd className="counter-serving-token">
                    {c.serving_token ?? "None"}
                  </dd>
                </div>
                <div>
                  <dt>Shared service queue</dt>
                  <dd>{c.waiting_count} waiting</dd>
                </div>
              </dl>
              {renderActions?.(c)}
            </article>
          );
        })}
      </div>
      {!visible.length && (
        <p className="empty">No counters configured for this service.</p>
      )}
    </section>
  );
}
