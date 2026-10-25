// The refusals the server names by a code (`code` in its error body,
// app/api/errors.py) that the page says in its own German words instead of
// quoting the server's English. A code not listed here gets the caller's
// sentence and the English reason; tests/refusals.test.ts checks that every code
// listed is one the backend sends.
import { t, type MessageParams } from "@/i18n/de";

export const REFUSAL_CODES = [
  "forbidden",
  "service_unavailable",
  "validation_failed",
  // an upload or an import (backend app/api/sources.py), and a body cut at its limit
  "file_too_large",
  "content_too_large",
  "archive_too_large",
  "unsupported_type",
  "file_missing",
  "title_invalid",
  "title_too_long",
  "url_invalid",
  "too_many_uploads",
  "too_many_imports",
  // an entry's content and its conversion (backend app/api/source_content.py, conversions.py)
  "file_hidden",
  "no_file",
  "not_pdf",
  "too_many_conversions",
  "no_conversion",
  "not_converted",
  "no_such_page",
  // a document and its extraction (backend app/api/documents.py), a model job's admission (limits.py)
  "no_document",
  "not_owner",
  "unknown_sector",
  "unknown_region",
  "no_budget",
  "too_many_jobs",
  "too_many_starts",
  // a document's repair (backend app/api/documents.py)
  "not_checked",
  "nothing_to_repair",
] as const;

export type RefusalCode = (typeof REFUSAL_CODES)[number];

function isRefusalCode(code: unknown): code is RefusalCode {
  return (REFUSAL_CODES as readonly unknown[]).includes(code);
}

/** The page's words for a refusal the server named by its code; null for any other code. */
export function refusalText(code: unknown, params: MessageParams = {}): string | null {
  return isRefusalCode(code) ? t(`refusals.${code}`, params) : null;
}
