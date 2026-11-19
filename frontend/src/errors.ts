export type ErrorEvent = { source: string; message?: string };
const listeners = new Set<(event: ErrorEvent) => void>();
export function publishError(event: ErrorEvent) {
  listeners.forEach((listener) => listener(event));
}
export function subscribeErrors(listener: (event: ErrorEvent) => void) {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}
export function apiMessage(status: number, detail: unknown): string {
  if (status >= 500)
    return "The server could not complete the request. Please try again.";
  if (Array.isArray(detail)) {
    if (detail.some((e) => String(e?.msg).toLowerCase().includes("email")))
      return "Enter a valid email address for email notifications.";
    return [
      ...new Set(
        detail.map((e) => {
          const field = Array.isArray(e?.loc)
            ? e.loc.filter((p: unknown) => p !== "body").join(" ")
            : "";
          return `${field ? `${field}: ` : ""}${typeof e?.msg === "string" ? e.msg : "Check the supplied value."}`;
        }),
      ),
    ].join(" ");
  }
  return typeof detail === "string"
    ? detail
    : "Unable to complete the request. Please try again.";
}
