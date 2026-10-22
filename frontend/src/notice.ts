// What the page says about an action: a sentence in German, and why, when an
// action failed and the server said why.
import { t } from "@/i18n/de";
import { refusalText } from "@/refusals";

/**
 * A sentence for the page, and the server's reason apart from it.
 *
 * The reason is kept apart because it is English - the API speaks English - and
 * a passage in another language has to be marked as one (WCAG 3.1.2), or a
 * screen reader reads it with German sounds. NoticeText shows it as a quotation
 * after the sentence. A refusal the page knows is said in its own words
 * instead: the `explanation`, German and unquoted.
 */
export interface Notice {
  text: string;
  reason?: string;
  explanation?: string;
  /** Set on a failure, so a line that says both kinds can colour it as one. */
  failed?: boolean;
}

/** What a caller may say in its own words instead of the general ones. */
export interface FailureWords {
  /** A 429: which limit was reached, and the wait where the answer names it in seconds. */
  tooManyRequests?: (seconds?: number) => string;
}

/** What the notice reads of a failure; anything thrown may arrive here. */
interface Failure {
  kind?: unknown;
  status?: unknown;
  code?: unknown;
  sentence?: unknown;
  retryAfter?: unknown;
}

/**
 * A failed action's notice: the caller's sentence, and why - in German for a
 * refusal the page knows, for a wait or a lost connection, else the server's
 * own sentence where it sent one.
 */
export function failureNotice(error: unknown, text: string = t("states.errorTitle"), words: FailureWords = {}): Notice {
  const failure = (error ?? {}) as Failure;
  const explanation = refusalText(failure.code);
  if (explanation) return { text, explanation, failed: true };
  if (failure.kind === "network") return { text, explanation: t("states.offline"), failed: true };
  const seconds = typeof failure.retryAfter === "number" ? failure.retryAfter : undefined;
  if (words.tooManyRequests && failure.status === 429) {
    return { text, explanation: words.tooManyRequests(seconds), failed: true };
  }
  if (seconds !== undefined) return { text, explanation: t("states.tooManyRequests", { count: seconds }), failed: true };
  // Only the server's sentence: a plain Error's message is a programmer's, not a reader's.
  const reason = typeof failure.sentence === "string" ? failure.sentence : "";
  return reason ? { text, reason, failed: true } : { text, failed: true };
}
