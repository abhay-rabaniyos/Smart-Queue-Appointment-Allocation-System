import type { Board, Service } from "../api";
import CounterOverview from "./CounterOverview";
export default function QueueBoard({
  board,
  services,
}: {
  board: Board | null;
  services: Service[];
}) {
  return (
    <>
      <CounterOverview
        counters={board?.counters ?? []}
        title="Now serving by counter"
      />
      <section className="panel">
        <h2>Up next</h2>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Token</th>
                <th>Service</th>
                <th>Counter routing</th>
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
                    <td>
                      {board.counters
                        .filter(
                          (c) =>
                            c.service_id === t.service_id &&
                            ["available", "serving"].includes(c.availability),
                        )
                        .map((c) => c.name)
                        .join(" / ") || "Awaiting an available counter"}
                      <small>Assigned when called</small>
                    </td>
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
