// What a conversion found in a file's text, and why one failed, in the page's words. A finding
// is a code with its numbers (backend app/conversion/symbols.py, encoding.py, assemble.py); the
// page says it only where the numbers are there, and by its code where they are not: a sentence
// filled with guesses would read as confident nonsense.
import type { ConversionFinding } from "@/api";
import { isolate } from "@/bidi";
import { LOCALE, messages, t } from "@/i18n/de";
import { jobFailureText } from "@/jobMessages";

const listFormat = new Intl.ListFormat(LOCALE, { type: "conjunction" });
const shareFormat = new Intl.NumberFormat(LOCALE, { style: "percent", maximumFractionDigits: 1 });

function isPageList(value: unknown): value is number[] {
  return Array.isArray(value) && value.length > 0 && value.every((page) => Number.isInteger(page));
}

/** Pages as a reader counts them: 1, 2, 3, 5 is "1–3 und 5" - a symbol font's bullet stands on many. */
function pageRanges(pages: number[]): string {
  const runs: [number, number][] = [];
  for (const page of [...pages].sort((a, b) => a - b)) {
    const last = runs[runs.length - 1];
    if (last && page === last[1] + 1) last[1] = page;
    else if (!last || page !== last[1]) runs.push([page, page]);
  }
  return listFormat.format(runs.map(([from, to]) => (from === to ? String(from) : t("conversions.pageRange", { from, to }))));
}

function symbolText({ codepoint, count, pages }: Record<string, unknown>): string | null {
  if (typeof codepoint !== "string" || typeof count !== "number" || !isPageList(pages)) return null;
  return t("conversions.findings.unmapped_symbol", { count, codepoint, pageCount: pages.length, pages: pageRanges(pages) });
}

function encodingText({ share, count, examples }: Record<string, unknown>): string | null {
  if (typeof share !== "number" || typeof count !== "number") return null;
  if (!Array.isArray(examples) || examples.length === 0) return null;
  if (!examples.every((example) => typeof example === "string")) return null;
  // the document's own signs: quoted, and isolated, so a sign of another script turns no sentence round
  const quoted = listFormat.format(examples.map((example) => t("conversions.quoted", { text: isolate(example) })));
  return t("conversions.findings.encoding_suspect", { count, share: shareFormat.format(share), examples: quoted });
}

/** Words left out of the blocks, by why: a reason the page has no words for is said by its code. */
function droppedText({ reason, count, pages }: Record<string, unknown>): string | null {
  if (typeof reason !== "string" || !Object.hasOwn(messages.conversions.findings.text_dropped, reason)) return null;
  if (typeof count !== "number" || !isPageList(pages)) return null;
  return t(`conversions.findings.text_dropped.${reason}`, { count, pageCount: pages.length, pages: pageRanges(pages) });
}

const FINDINGS: Readonly<Record<string, (params: Record<string, unknown>) => string | null>> = {
  unmapped_symbol: symbolText,
  encoding_suspect: encodingText,
  text_dropped: droppedText,
};

/** A finding in words; by its code where the page has no words for it, or its numbers are missing. */
export function findingText({ code, params }: ConversionFinding): string {
  return FINDINGS[code]?.(params) ?? t("conversions.findings.other", { code });
}

/**
 * Why a conversion failed: its job's reason, or that the job was stopped. A job that failed again
 * and again failed on the service here - a conversion asks no other server, as a fetch does.
 */
export function conversionFailureText(code: string | null): string {
  if (code === "cancelled") return t("conversions.cancelled");
  if (code === "handler_error") return t("conversions.handlerError");
  return jobFailureText(code);
}
