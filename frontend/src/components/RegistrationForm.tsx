import { useEffect, useState, type FormEvent } from "react";
import {
  ArrowRight,
  CalendarDays,
  Check,
  Ticket as TicketIcon,
} from "lucide-react";
import { api, type Service } from "../api";
import { today, formatTime } from "../utils";
export default function RegistrationForm({
  services,
  reception,
  busy,
  onSubmit,
}: {
  services: Service[];
  reception: boolean;
  busy: boolean;
  onSubmit: (data: unknown) => Promise<void>;
}) {
  const [mode, setMode] = useState("appointment"),
    [service, setService] = useState(""),
    [day, setDay] = useState(today()),
    [slots, setSlots] = useState<{ time: string; remaining: number }[]>([]),
    [slot, setSlot] = useState(""),
    [slotError, setSlotError] = useState("");
  const chosen = service || services[0]?.id || "";
  useEffect(() => {
    let cancelled = false;
    setSlots([]);
    setSlot("");
    setSlotError("");
    if (chosen && day && mode === "appointment")
      api<{ time: string; remaining: number }[]>(
        `/services/${chosen}/slots?day=${day}`,
      )
        .then((v) => {
          if (!cancelled) setSlots(v);
        })
        .catch((e) => {
          if (!cancelled) setSlotError(e.message);
        });
    return () => {
      cancelled = true;
    };
  }, [chosen, day, mode]);
  const submit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const data = new FormData(e.currentTarget);
    void onSubmit({
      service_id: chosen,
      name: data.get("name"),
      contact: data.get("contact") || "",
      channel: data.get("channel"),
      source: mode,
      priority: reception ? Number(data.get("priority")) : 0,
      slot: mode === "appointment" ? slot : null,
    });
  };
  return (
    <form onSubmit={submit}>
      <div className="segmented">
        <button
          type="button"
          className={mode === "appointment" ? "active" : ""}
          onClick={() => setMode("appointment")}
        >
          <CalendarDays size={17} />
          Book appointment
        </button>
        <button
          type="button"
          className={mode === "walk_in" ? "active" : ""}
          onClick={() => setMode("walk_in")}
        >
          <TicketIcon size={17} />
          Walk in
        </button>
      </div>
      <label>
        Select a service
        <select
          aria-label="Select a service"
          value={chosen}
          onChange={(e) => setService(e.target.value)}
          required
        >
          {!services.length && <option value="">No services available</option>}
          {services.map((s) => (
            <option key={s.id} value={s.id}>
              {s.name} · ~{s.minutes} min
            </option>
          ))}
        </select>
      </label>
      {mode === "appointment" && (
        <>
          <label>
            Preferred date
            <input
              aria-label="Preferred date"
              type="date"
              min={today()}
              value={day}
              onChange={(e) => setDay(e.target.value)}
              required
            />
          </label>
          <fieldset>
            <legend>Available time slots</legend>
            <div className="slots">
              {slots.map((s) => (
                <button
                  type="button"
                  key={s.time}
                  aria-pressed={slot === s.time}
                  disabled={!s.remaining}
                  className={slot === s.time ? "chosen" : ""}
                  onClick={() => setSlot(s.time)}
                >
                  {formatTime(s.time)}
                  <small>{s.remaining ? `${s.remaining} left` : "Full"}</small>
                </button>
              ))}
            </div>
            {!slots.length && (
              <p className="muted">
                {slotError ||
                  "No upcoming slots on this date. Choose another day."}
              </p>
            )}
          </fieldset>
        </>
      )}
      <div className="form-row">
        <label>
          Full name
          <input
            name="name"
            placeholder="e.g. Alex Thomas"
            minLength={2}
            maxLength={100}
            required
            autoComplete="name"
          />
        </label>
        <label>
          Notification channel
          <select name="channel" defaultValue="email">
            <option value="email">Email</option>
            <option value="sms">SMS</option>
            <option value="whatsapp">WhatsApp</option>
          </select>
        </label>
      </div>
      <label>
        Contact for updates <span className="optional">(optional)</span>
        <input
          name="contact"
          placeholder="Email address or +91 phone number"
          maxLength={254}
        />
      </label>
      {reception && (
        <label>
          Staff-assigned priority
          <select name="priority">
            <option value="0">Standard</option>
            <option value="1">Priority</option>
            <option value="2">Urgent · requires human assessment</option>
          </select>
        </label>
      )}
      <div className="form-note">
        <Check size={16} />
        <span>
          Save your queue pass to manage your visit. Contact details are used
          only for service updates.
        </span>
      </div>
      <button
        className="primary wide"
        disabled={busy || !chosen || (mode === "appointment" && !slot)}
      >
        {busy
          ? "Please wait…"
          : mode === "appointment"
            ? "Confirm appointment"
            : "Get walk-in token"}
        <ArrowRight size={18} />
      </button>
    </form>
  );
}
