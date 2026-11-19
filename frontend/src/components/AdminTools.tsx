import { useRef, type FormEvent } from "react";
import { Plus } from "lucide-react";
import { api } from "../api";
import type { Operations } from "../types";
import { status } from "../utils";
export default function AdminTools({
  ops,
  busy,
  act,
  reloadServices,
}: {
  ops: Operations;
  busy: boolean;
  act: (fn: () => Promise<unknown>, message?: string) => Promise<void>;
  reloadServices: () => Promise<unknown>;
}) {
  const ref = useRef<HTMLFormElement>(null);
  function submit(
    e: FormEvent<HTMLFormElement>,
    path: string,
    convert: (f: FormData) => unknown,
  ) {
    e.preventDefault();
    const form = e.currentTarget;
    void act(async () => {
      await api(path, "POST", convert(new FormData(form)));
      form.reset();
      await reloadServices();
    }, "Configuration saved");
  }
  return (
    <>
      <section className="panel">
        <h2>Administration</h2>
        <div className="admin-grid">
          <form
            onSubmit={(e) =>
              submit(e, "/admin/services", (f) => ({
                name: f.get("name"),
                minutes: Number(f.get("minutes")),
                capacity: Number(f.get("capacity")),
              }))
            }
          >
            <h3>Add service</h3>
            <label>
              Service name
              <input name="name" required minLength={2} />
            </label>
            <div className="form-row">
              <label>
                Slot minutes
                <input
                  name="minutes"
                  type="number"
                  min="1"
                  max="120"
                  defaultValue="10"
                  required
                />
              </label>
              <label>
                Slot capacity
                <input
                  name="capacity"
                  type="number"
                  min="1"
                  max="100"
                  defaultValue="2"
                  required
                />
              </label>
            </div>
            <button className="secondary" disabled={busy}>
              <Plus size={16} />
              Add service
            </button>
          </form>
          <form
            onSubmit={(e) =>
              submit(e, "/admin/staff", (f) => Object.fromEntries(f))
            }
          >
            <h3>Add staff member</h3>
            <label>
              Name
              <input name="name" minLength={2} required />
            </label>
            <label>
              Email
              <input name="email" type="email" required />
            </label>
            <label>
              Initial password
              <input
                name="password"
                type="password"
                minLength={12}
                maxLength={128}
                autoComplete="new-password"
                required
              />
            </label>
            <label>
              Role
              <select name="role">
                <option value="staff">Service staff</option>
                <option value="receptionist">Receptionist</option>
                <option value="admin">Administrator</option>
              </select>
            </label>
            <button className="secondary" disabled={busy}>
              <Plus size={16} />
              Add staff
            </button>
          </form>
          <form
            ref={ref}
            onSubmit={(e) =>
              submit(e, "/admin/counters", (f) => ({
                name: f.get("name"),
                service_id: f.get("service_id"),
                staff_id: f.get("staff_id") || null,
                active: true,
              }))
            }
          >
            <h3>Add counter</h3>
            <label>
              Counter name
              <input name="name" required />
            </label>
            <label>
              Service
              <select name="service_id" required>
                {ops.services
                  .filter((s) => s.active)
                  .map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.name}
                    </option>
                  ))}
              </select>
            </label>
            <label>
              Staff assignment
              <select name="staff_id">
                <option value="">Unassigned</option>
                {ops.staff
                  .filter((s) => s.active && s.role !== "receptionist")
                  .map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.name}
                    </option>
                  ))}
              </select>
            </label>
            <button className="secondary" disabled={busy}>
              <Plus size={16} />
              Add counter
            </button>
          </form>
        </div>
      </section>
      <section className="panel">
        <h2>Service configuration</h2>
        <p className="muted">
          Resolve active visits before changing a service’s schedule or
          availability.
        </p>
        {ops.services.map((service) => (
          <form
            className="allocation-row"
            key={`${service.id}-${service.active}-${service.minutes}-${service.capacity}`}
            onSubmit={(e) => {
              e.preventDefault();
              const f = new FormData(e.currentTarget);
              void act(async () => {
                await api(`/admin/services/${service.id}`, "PUT", {
                  name: service.name,
                  minutes: Number(f.get("minutes")),
                  capacity: Number(f.get("capacity")),
                  active: f.get("active") === "on",
                });
                await reloadServices();
              }, "Service updated");
            }}
          >
            <strong>{service.name}</strong>
            <label>
              Slot minutes
              <input
                name="minutes"
                type="number"
                min="1"
                max="120"
                defaultValue={service.minutes}
                required
              />
            </label>
            <label>
              Capacity
              <input
                name="capacity"
                type="number"
                min="1"
                max="100"
                defaultValue={service.capacity}
                required
              />
            </label>
            <label className="checkbox">
              <input
                type="checkbox"
                name="active"
                defaultChecked={service.active}
              />
              Active
            </label>
            <button className="secondary" disabled={busy}>
              Update
            </button>
          </form>
        ))}
      </section>
      <section className="panel">
        <h2>Staff & counter allocation</h2>
        {ops.counters.map((c) => (
          <form
            className="allocation-row"
            key={`${c.id}-${c.staff_id}-${c.active}`}
            onSubmit={(e) => {
              e.preventDefault();
              const f = new FormData(e.currentTarget);
              void act(
                () =>
                  api(`/admin/counters/${c.id}`, "PUT", {
                    name: c.name,
                    service_id: f.get("service_id"),
                    staff_id: f.get("staff_id") || null,
                    active: f.get("active") === "on",
                  }),
                "Counter updated",
              );
            }}
          >
            <strong>{c.name}</strong>
            <label>
              Service
              <select name="service_id" defaultValue={c.service_id}>
                {ops.services.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Staff
              <select name="staff_id" defaultValue={c.staff_id ?? ""}>
                <option value="">Unassigned</option>
                {ops.staff
                  .filter((s) => s.active && s.role !== "receptionist")
                  .map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.name}
                    </option>
                  ))}
              </select>
            </label>
            <label className="checkbox">
              <input type="checkbox" name="active" defaultChecked={c.active} />
              Open
            </label>
            <button className="secondary" disabled={busy}>
              Update
            </button>
          </form>
        ))}
        <div className="staff-list">
          {ops.staff.map((s) => (
            <div className="section-title" key={s.id}>
              <span>
                {s.name}{" "}
                <small className="muted">
                  {s.role} · {s.active ? "Active" : "Disabled"}
                </small>
              </span>
              <button
                className="text-button"
                disabled={busy}
                onClick={() =>
                  void act(
                    () =>
                      api(`/admin/staff/${s.id}`, "PUT", { active: !s.active }),
                    "Staff updated",
                  )
                }
              >
                {s.active ? "Disable" : "Enable"}
              </button>
            </div>
          ))}
        </div>
      </section>
      <section className="panel">
        <h2>Queue rules</h2>
        <p className="muted">
          Priority score = priority × weight + minutes waited ÷ aging interval.
          Waiting time increases priority without a cap.
        </p>
        <form
          className="rules"
          key={JSON.stringify(ops.rules)}
          onSubmit={(e) => {
            e.preventDefault();
            const f = new FormData(e.currentTarget);
            void act(
              () =>
                api(
                  "/admin/rules",
                  "PUT",
                  Object.fromEntries([...f].map(([k, v]) => [k, Number(v)])),
                ),
              "Queue rules saved",
            );
          }}
        >
          {Object.entries(ops.rules).map(([key, value]) => (
            <label key={key}>
              {key.replaceAll("_", " ")}
              <input
                name={key}
                type="number"
                min="1"
                max="120"
                defaultValue={value}
                required
              />
            </label>
          ))}
          <button className="primary" disabled={busy}>
            Save rules
          </button>
        </form>
      </section>
      <section className="panel">
        <h2>Notification delivery</h2>
        <p className="muted">
          “Simulated” means console mode. Configure SMTP or an HTTPS gateway for
          real delivery.
        </p>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Event</th>
                <th>State</th>
                <th>Attempts</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {ops.outbox.map((e) => (
                <tr key={e.id}>
                  <td>{status(e.kind)}</td>
                  <td>
                    {e.state}
                    {e.error && (
                      <small role="note">
                        {e.error_message ??
                          "Notification delivery failed. Check the provider configuration."}
                      </small>
                    )}
                  </td>
                  <td>{e.attempts}</td>
                  <td>
                    {e.state === "dead" && (
                      <button
                        className="text-button"
                        disabled={busy}
                        onClick={() =>
                          void act(
                            () => api(`/admin/outbox/${e.id}/retry`, "POST"),
                            "Retry scheduled",
                          )
                        }
                      >
                        Retry
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
      <section className="panel">
        <h2>Recent audit activity</h2>
        {ops.audit.slice(0, 12).map((a) => (
          <div className="audit-row" key={a.id}>
            <span>{status(a.action)}</span>
            <small>{new Date(a.created).toLocaleString()}</small>
          </div>
        ))}
      </section>
    </>
  );
}
