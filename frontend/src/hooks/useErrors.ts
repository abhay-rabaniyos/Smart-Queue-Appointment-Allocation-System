import { useCallback, useEffect, useState } from "react";
import { subscribeErrors } from "../errors";
type Incident = { source: string; message: string; dismissed: boolean };
export default function useErrors() {
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const report = useCallback(
    (source: string, message: string) =>
      setIncidents((previous) => {
        if (previous.some((e) => e.source === source && e.message === message))
          return previous;
        const hidden = previous.some(
          (e) => e.message === message && e.dismissed,
        );
        return [
          ...previous.filter((e) => e.source !== source),
          { source, message, dismissed: hidden },
        ];
      }),
    [],
  );
  const resolve = useCallback(
    (source: string) =>
      setIncidents((previous) =>
        previous.some((e) => e.source === source)
          ? previous.filter((e) => e.source !== source)
          : previous,
      ),
    [],
  );
  const dismiss = useCallback(
    (message: string) =>
      setIncidents((previous) =>
        previous.map((e) =>
          e.message === message ? { ...e, dismissed: true } : e,
        ),
      ),
    [],
  );
  useEffect(
    () =>
      subscribeErrors((e) =>
        e.message ? report(e.source, e.message) : resolve(e.source),
      ),
    [report, resolve],
  );
  return {
    messages: [
      ...new Set(incidents.filter((e) => !e.dismissed).map((e) => e.message)),
    ],
    report,
    resolve,
    dismiss,
  };
}
