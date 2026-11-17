import type React from "react";
export default function Stat({
  icon,
  label,
  value,
  note,
}: {
  icon?: React.ReactNode;
  label: string;
  value: string;
  note: string;
}) {
  return (
    <article className="stat">
      <div>
        <span>{label}</span>
        {icon && <span className="stat-icon">{icon}</span>}
      </div>
      <strong>{value}</strong>
      <small>{note}</small>
    </article>
  );
}
