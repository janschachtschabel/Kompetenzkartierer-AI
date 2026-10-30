// A statement's anchors as its draft holds them (plan M1 9.8, Paket 9c2b L2): each a code - the blocks of the
// conversion it stands in (`blocks:p5-b2,p5-b3`), or the page it stands on where no block holds it (`page:5`) -
// so that a list of them compares, rebases and is kept like any field of many. Read off the anchors stored,
// sent as the anchors an edit names (backend AnchorIn), said in words.
import type { AnchorIn, TreeAnchor } from "@/api";
import { pagesText } from "@/anchorWords";
import { t } from "@/i18n/de";

const BLOCKS = "blocks:";
const PAGE = "page:";
// as the backend takes them (app/api/statement_editing.py BlockId, MOST_PAGE): pages from 1
const BLOCK_ID = /^p([1-9][0-9]{0,4})-b[0-9]{1,6}$/;
const PAGE_NUMBER = /^[1-9][0-9]{0,4}$/;

export function encodeAnchor(anchor: AnchorIn): string {
  return "blocks" in anchor ? BLOCKS + anchor.blocks.join(",") : PAGE + String(anchor.page);
}

/** The anchor a code names; none for one written otherwise. */
export function decodeAnchor(code: string): AnchorIn | null {
  if (code.startsWith(PAGE)) {
    const page = code.slice(PAGE.length);
    return PAGE_NUMBER.test(page) ? { page: Number(page) } : null;
  }
  if (!code.startsWith(BLOCKS)) return null;
  const blocks = code.slice(BLOCKS.length).split(",");
  return blocks.every((id) => BLOCK_ID.test(id)) ? { blocks } : null;
}

/** The page a block's id names; none for an id written otherwise. */
export function pageOfBlock(id: string): number | null {
  const found = BLOCK_ID.exec(id);
  return found ? Number(found[1]) : null;
}

/**
 * The codes of a row's stored anchors, each place once. simplify: an anchor with neither blocks nor a page
 * cannot be named in an edit (AnchorIn), so it is left out - a change of the anchors goes without it; the
 * row's detail still shows it as stored.
 */
export function anchorsOf(anchors: readonly TreeAnchor[]): string[] {
  const codes = anchors.flatMap((anchor) => {
    if (anchor.blocks.length) return [encodeAnchor({ blocks: anchor.blocks })];
    return anchor.page_start === null ? [] : [encodeAnchor({ page: anchor.page_start })];
  });
  return [...new Set(codes)];
}

/** The anchors an edit names, in the draft's order; the codes are the draft's own (`anchorsOf`, `encodeAnchor`). */
export function anchorRequest(codes: readonly string[]): AnchorIn[] {
  return codes.map(decodeAnchor).filter((anchor): anchor is AnchorIn => anchor !== null);
}

/** A code in words: its pages and how many blocks, or the page its passage was not found on. */
export function anchorCodeText(code: string): string {
  const anchor = decodeAnchor(code);
  if (!anchor) return code;
  if ("page" in anchor) {
    return t("documents.tree.anchors.draftPage", { pages: pagesText({ page_start: anchor.page, page_end: null, printed_page: null }) });
  }
  const pages = anchor.blocks.map((id) => pageOfBlock(id) ?? 0);
  const first = Math.min(...pages);
  const last = Math.max(...pages);
  const where = pagesText({ page_start: first, page_end: last, printed_page: null });
  return t("documents.tree.anchors.draftBlocks", { pages: where, count: anchor.blocks.length });
}
