import type { Ticket, Counter, Service, User } from "./api";
export type Operations = {
  tickets: Ticket[];
  counters: Counter[];
  services: Service[];
  staff: (User & { email: string; active: boolean })[];
  rules: {
    aging_minutes: number;
    priority_weight: number;
    grace_minutes: number;
  };
  analytics: {
    completed: number;
    average_wait: number;
    waiting: number;
    no_shows: number;
    sample_limit: number;
  };
  outbox: {
    id: string;
    kind: string;
    state: string;
    attempts: number;
    error: string | null;
  }[];
  audit: { id: string; action: string; actor: string; created: string }[];
};
