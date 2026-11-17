import type { Board, Service } from "../api";
export default function QueueBoard({
  board,
  services,
}: {
  board: Board | null;
  services: Service[];
}) {
  return (
    <>
      <section className="panel">
        <div className="section-title">
          <h2>Now serving</h2>
          <span className="eyebrow">WATCH FOR YOUR TOKEN</span>
        </div>
        <div className="counter-grid">
          {board?.counters.map((c) => {
            const t = board.tickets.find(
              (t) => t.counter_id === c.id && t.status === "serving",
            );
            return (
              <article className="counter-card" key={c.id}>
                <span
                  className={`badge ${c.active && c.staffed ? "waiting" : "cancelled"}`}
                >
                  {c.active && c.staffed ? "Open" : "Unavailable"}
                </span>
                <h3>{c.name}</h3>
                <strong className="counter-token">{t?.token ?? "—"}</strong>
                <p>{services.find((s) => s.id === c.service_id)?.name}</p>
              </article>
            );
          })}
        </div>
        {!board?.counters.length && (
          <p className="empty">No counters configured yet.</p>
        )}
      </section>
      <section className="panel">
        <h2>Up next</h2>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Token</th>
                <th>Service</th>
                <th>Position</th>
                <th>Estimated wait</th>
              </tr>
            </thead>
            <tbody>
              {board?.tickets
                .filter((t) => t.status === "waiting")
                .sort((a, b) => (a.position ?? 0) - (b.position ?? 0))
                .map((t) => (
                  <tr key={t.token}>
                    <td>
                      <strong>{t.token}</strong>
                    </td>
                    <td>{services.find((s) => s.id === t.service_id)?.name}</td>
                    <td>{t.position}</td>
                    <td>
                      {t.eta_minutes === null
                        ? "Awaiting a staffed counter"
                        : `${t.eta_minutes} min`}
                    </td>
                  </tr>
                ))}
            </tbody>
          </table>
          {!board?.tickets.some((t) => t.status === "waiting") && (
            <p className="empty">A clear queue. You’re right on time.</p>
          )}
        </div>
      </section>
    </>
  );
}
