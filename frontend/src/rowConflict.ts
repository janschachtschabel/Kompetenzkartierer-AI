// Two changes to one row of a document's tree, laid side by side (plan M1 9.8, Paket 9c2 K5; after the old
// app's nodeConflict.ts). A change names the revision its form was filled from; where somebody changed the row
// since, the server refuses it and answers with the row as stored (409 stale_revision, details.current). Each
// field the other changed and the user did not is taken in, and named, so the user saves it knowingly; each
// field both changed, to different values, is put before the user to decide; a field only the user changed
// stays theirs. Compared as the server stores them (rowDraft.sameValue).
import type { FormField } from "@/api";
import { sameValue, type Draft } from "@/rowDraft";

/** A field both changed, to different values. */
export interface Clash {
  key: string;
  yours: string | string[];
  stored: string | string[];
}

export interface Rebased {
  /** The user's draft with what only the other changed taken in; a clash keeps the user's value until decided. */
  draft: Draft;
  /** In the order of the form. */
  clashes: Clash[];
  /** The fields only the other changed, in the order of the form. */
  taken: string[];
}

/** Lay `draft` - the user's form, begun from `before` - beside `stored`, the row as the server holds it now. */
export function rebase(fields: readonly FormField[], before: Draft, draft: Draft, stored: Draft): Rebased {
  const merged: Draft = { ...draft };
  const clashes: Clash[] = [];
  const taken: string[] = [];
  for (const { key } of fields) {
    const was = before[key];
    const yours = draft[key];
    const now = stored[key];
    if (sameValue(now, was) || sameValue(now, yours)) continue;
    if (sameValue(yours, was)) {
      merged[key] = Array.isArray(now) ? [...now] : now;
      taken.push(key);
    } else clashes.push({ key, yours, stored: now });
  }
  return { draft: merged, clashes, taken };
}
