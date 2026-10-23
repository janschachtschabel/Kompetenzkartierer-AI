// Which page of a converted file the blocks' view shows: it is in the address (`?seite=3`), and
// the first page has none, so the first page's address is the view's own.
export const PAGE_PARAM = "seite";

/** The query of the address that shows page `page`. */
export function pageQuery(page: number): Record<string, string> {
  return page === 1 ? {} : { [PAGE_PARAM]: String(page) };
}
