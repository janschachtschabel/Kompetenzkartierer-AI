// What the register shows (RegisterFilter.vue), and what that asks of the server.
import type { RegisterStatus, SourceFilters } from "@/api";
import { t } from "@/i18n/de";

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

/** What to do where `asked` let no entry through: take back what it set. */
export function emptyAdvice(asked: SourceFilters): string {
  const label = t("sources.filter.candidates");
  if (asked.candidates && asked.status) return t("sources.filter.emptyBody.both", { label });
  if (asked.candidates) return t("sources.filter.emptyBody.candidates", { label });
  return t("sources.filter.emptyBody.status", { any: t("sources.filter.anyStatus") });
}

/** Whether two questions to the server ask for the same entries. */
export function sameAsked(a: SourceFilters, b: SourceFilters): boolean {
  const names = new Set([...Object.keys(a), ...Object.keys(b)]) as Set<keyof SourceFilters>;
  return [...names].every((name) => a[name] === b[name]);
}
