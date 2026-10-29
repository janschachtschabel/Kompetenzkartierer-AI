// The review statuses of nodes and statements (cv:ReviewStatuses, backend ontology/ontologie/cur-vokabular.ttl):
// proposed until an editor confirms or rejects a row; the tree shows them in words and as a tone.
import { messages } from "@/i18n/de";
import { word } from "@/registerWords";

export const CV = "https://w3id.org/wlo/curriculum/vocab#";

export const REVIEW_STATUSES = ["proposed", "confirmed", "rejected"] as const;
export type ReviewStatus = (typeof REVIEW_STATUSES)[number];

/** The tone of a status badge (style.css, .status-badge): never the only sign, its word stands beside it. */
export const REVIEW_TONES: Record<ReviewStatus, "neutral" | "success" | "error"> = {
  proposed: "neutral",
  confirmed: "success",
  rejected: "error",
};

export function statusIri(status: ReviewStatus): string {
  return `${CV}rev_${status}`;
}

/** The status an IRI names; none for one the vocabulary does not hold. */
export function statusOf(iri: string): ReviewStatus | null {
  return REVIEW_STATUSES.find((status) => statusIri(status) === iri) ?? null;
}

/** The status in words; one the vocabulary does not hold as it is. */
export function statusWord(iri: string): string {
  return word(messages.documents.tree.statuses, statusOf(iri) ?? iri);
}
