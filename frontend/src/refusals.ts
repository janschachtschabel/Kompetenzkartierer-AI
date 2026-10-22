// The refusals the server names by a code (`code` in its error body,
// app/api/errors.py) that the page says in its own German words instead of
// quoting the server's English. A code not listed here gets the caller's
// sentence and the English reason; tests/refusals.test.ts checks that every code
// listed is one the backend sends.
import { t, type MessageParams } from "@/i18n/de";

export const REFUSAL_CODES = ["forbidden", "service_unavailable", "validation_failed"] as const;

export type RefusalCode = (typeof REFUSAL_CODES)[number];

function isRefusalCode(code: unknown): code is RefusalCode {
  return (REFUSAL_CODES as readonly unknown[]).includes(code);
}

/** The page's words for a refusal the server named by its code; null for any other code. */
export function refusalText(code: unknown, params: MessageParams = {}): string | null {
  return isRefusalCode(code) ? t(`refusals.${code}`, params) : null;
}
