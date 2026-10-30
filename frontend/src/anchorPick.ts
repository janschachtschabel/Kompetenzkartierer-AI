// Choosing a statement's anchor in the source (plan M1 9.8, Paket 9c2b L3): the blocks chosen on the page
// shown, each toggled, taken as one anchor - its code, anchorDraft.ts. The choice is not content (L10: no leave
// guard asks about it); it goes with whatever `resets` names - the page shown, the statement it is for.
import { shallowRef, watch, type WatchSource } from "vue";

import { encodeAnchor } from "@/anchorDraft";

export function useAnchorPick(resets: WatchSource[]) {
  const picked = shallowRef<ReadonlySet<string>>(new Set());

  watch(resets, () => {
    picked.value = new Set();
  });

  function toggle(id: string): void {
    const now = new Set(picked.value);
    if (!now.delete(id)) now.add(id);
    picked.value = now;
  }

  /** The code of the blocks chosen, as one anchor, the choice let go; none while none is chosen. */
  function take(): string | null {
    if (!picked.value.size) return null;
    const code = encodeAnchor({ blocks: [...picked.value] });
    picked.value = new Set();
    return code;
  }

  return { picked, toggle, take };
}
