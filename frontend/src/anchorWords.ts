// An anchor in words (plan M1 9.9, Paket 9c J8): its pages, the one the document prints beside, and how its
// passage was found (cv:MatchKinds, backend ontology/ontologie/cur-vokabular.ttl) - none yet before X5 looked.
import type { TreeAnchor } from "@/api";
import { LOCALE, messages, t } from "@/i18n/de";
import { CV } from "@/reviewStatus";
import { conceptWord } from "@/registerWords";

const MATCH = `${CV}match_`;
const PERCENT = new Intl.NumberFormat(LOCALE, { style: "percent", maximumFractionDigits: 0 });

/** How the passage was found; one the vocabulary does not hold as it is. */
export function matchWord(iri: string | null): string {
  return iri === null
    ? t("documents.tree.anchors.unchecked")
    : conceptWord(messages.documents.tree.anchors.matches, MATCH, iri);
}

/** How it was found, with how close a fuzzy match came. */
export function matchText(anchor: TreeAnchor): string {
  const found = matchWord(anchor.match_kind);
  if (anchor.match_kind !== `${MATCH}fuzzy` || anchor.match_score === null) return found;
  return t("documents.tree.anchors.scored", { found, score: PERCENT.format(anchor.match_score) });
}

/** Its physical pages, and the page the document prints where it prints one. */
export function pagesText(anchor: TreeAnchor): string {
  const { page_start: first, page_end: last, printed_page: printed } = anchor;
  if (first === null) return t("documents.tree.anchors.noPage");
  const pages =
    last === null || last === first
      ? t("documents.tree.anchors.page", { page: first })
      : t("documents.tree.anchors.pages", { first, last });
  return printed ? t("documents.tree.anchors.printed", { pages, printed }) : pages;
}
