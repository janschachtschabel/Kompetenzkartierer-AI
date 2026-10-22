// What the register shows (RegisterFilter.vue), and what that asks of the server.
import type { RegisterStatus, SourceFilters } from "@/api";

export interface RegisterFilters {
  candidates: boolean;
  /** Empty for every status. */
  status: RegisterStatus | "";
}

/** The statuses the filter offers, in the order an entry passes through them. */
export const STATUSES: readonly RegisterStatus[] = ["unchecked", "reachable", "unreachable", "acquired"];

/** What the filter asks of the server: only what it sets. */
export function askedOf(filters: RegisterFilters): SourceFilters {
  const query: SourceFilters = {};
  if (filters.candidates) query.candidates = true;
  if (filters.status) query.status = filters.status;
  return query;
}

/** Whether two questions to the server ask for the same entries. */
export function sameAsked(a: SourceFilters, b: SourceFilters): boolean {
  const names = new Set([...Object.keys(a), ...Object.keys(b)]) as Set<keyof SourceFilters>;
  return [...names].every((name) => a[name] === b[name]);
}
