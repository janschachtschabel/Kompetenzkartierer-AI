// Which page of a converted file a view shows: it is in the address (`?seite=3`). The blocks' view
// gives the first page none, so its address is the view's own; the document's tree reads an address
// without a page as the page of the row's first anchor, so a link that keeps the rest of an address
// names page 1 too (BlockList).
export const PAGE_PARAM = "seite";
// the last page the API reads (`page` up to 100000, app/api/conversions.py): past it, asking is refused
const LAST_PAGE = 100_000;

/** The page an address names: a whole number from 1 to LAST_PAGE as the views write it ("7", not "007",
 * "0x10" or "1e3"), else none. */
export function pageOf(value: unknown): number | null {
  return typeof value === "string" && /^[1-9]\d{0,5}$/.test(value) && Number(value) <= LAST_PAGE ? Number(value) : null;
}

/** The query of the address that shows page `page`. */
export function pageQuery(page: number): Record<string, string> {
  return page === 1 ? {} : { [PAGE_PARAM]: String(page) };
}
