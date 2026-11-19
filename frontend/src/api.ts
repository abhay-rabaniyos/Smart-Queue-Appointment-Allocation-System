import { publishError, apiMessage } from "./errors";
export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}
const uncertainCommands = new Map<string, string>();
export async function api<T = unknown>(
  path: string,
  method = "GET",
  body?: unknown,
  key?: string,
): Promise<T> {
  const fingerprint = JSON.stringify([method, path, body]);
  const commandKey =
    key ?? uncertainCommands.get(fingerprint) ?? crypto.randomUUID();
  if (method !== "GET") uncertainCommands.set(fingerprint, commandKey);
  const source = `${method}:${path}`;
  let response: Response;
  try {
    response = await fetch(`/api${path}`, {
      method,
      credentials: "include",
      signal: AbortSignal.timeout(15000),
      headers: {
        ...(body !== undefined ? { "Content-Type": "application/json" } : {}),
        ...(method !== "GET" ? { "Idempotency-Key": commandKey } : {}),
      },
      ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
    });
  } catch (error) {
    const message =
      error instanceof DOMException &&
      ["TimeoutError", "AbortError"].includes(error.name)
        ? "The request timed out. Please try again."
        : "Cannot connect to QueuePilot. Check your connection and try again.";
    publishError({ source, message });
    throw new ApiError(0, message);
  }
  if (response.status >= 400 && response.status < 500)
    uncertainCommands.delete(fingerprint);
  if (!response.ok) {
    const data = await response
      .json()
      .catch(() => ({ detail: "Unable to reach QueuePilot" }));
    const message = apiMessage(response.status, data?.detail);
    if (!(path === "/auth/me" && response.status === 401))
      publishError({ source, message });
    throw new ApiError(response.status, message);
  }
  try {
    const result = await response.json();
    uncertainCommands.delete(fingerprint);
    publishError({ source });
    return result;
  } catch {
    const message =
      "The server returned an unreadable response. Please try again.";
    publishError({ source, message });
    throw new ApiError(response.status, message);
  }
}
export type Service = {
  id: string;
  name: string;
  minutes: number;
  capacity: number;
  active: boolean;
};
export type Ticket = {
  id: string;
  secret: string;
  token: string;
  name: string;
  service_id: string;
  service_name?: string;
  notification_error?: { code: string; message: string; state: string } | null;
  status: string;
  slot: string | null;
  counter_id: string | null;
  priority: number;
  position: number | null;
  eta_minutes: number | null;
};
export type Counter = {
  id: string;
  name: string;
  service_id: string;
  staff_id?: string | null;
  active: boolean;
  staffed?: boolean;
};
export type Board = {
  organization: string;
  tickets: Omit<Ticket, "secret" | "name" | "id" | "priority" | "slot">[];
  counters: CounterSummary[];
};
export type CounterSummary = Counter & {
  service_name: string;
  service_active: boolean;
  availability:
    "available" | "serving" | "paused" | "unstaffed" | "service_unavailable";
  serving_token: string | null;
  waiting_count: number;
};
export type User = {
  id: string;
  name: string;
  role: "admin" | "receptionist" | "staff";
};
