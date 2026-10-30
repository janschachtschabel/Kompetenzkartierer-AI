// What a section of a page reads for itself (DocumentUnits.vue): read again whenever the page asks;
// what is shown stays meanwhile, and stays where a later reading fails, said beside it. The latest
// reading counts: an answer overtaken by a later question is dropped. A retry the reader asks for
// shows its waiting where nothing is shown yet, says a failure again even in the same words, and
// takes the keyboard to the section's heading once its button went with the notice; a retry a
// later reading overtook leaves both to that reading. Content no longer the reader's (403 file_hidden) is
// said apart: no retry changes it.
import { ref, shallowRef, watch, type Ref } from "vue";

import { ApiError } from "@/api";
import { focusIsFree } from "@/focusRescue";
import { sayAnew } from "@/liveRegion";
import { failureNotice, type Notice } from "@/notice";

export interface SectionReading<T> {
  /** What the last reading that counted gave; null before the first. */
  shown: Ref<T | null>;
  failure: Ref<Notice | null>;
  /** The last reading was refused for the entry's content no longer the reader's: no retry changes it. */
  hidden: Ref<boolean>;
  /** A reading is under way whose answer has not come: what is shown may be overtaken. */
  pending: Ref<boolean>;
  /** A reading as the page moves on: neither waiting nor keyboard change. */
  load: () => Promise<void>;
  /** A reading the reader asked for. */
  retry: () => Promise<void>;
}

/** `read` asks for what the section shows; `loadFailed` says that it did not come. */
export function useSectionReading<T>(
  read: () => Promise<T>,
  loadFailed: string,
  heading: Ref<HTMLElement | null>,
): SectionReading<T> {
  const shown = shallowRef<T | null>(null);
  const failure = ref<Notice | null>(null);
  const hidden = ref(false);
  const pending = ref(false);
  let generation = 0;
  // where the reader's retry began, until what it asked for is shown; undefined: none asked
  let retriedFrom: Element | null | undefined;
  // the notice the reader's retry began from, until a reading that counts answers it; undefined: none
  let retriedNotice: Notice | null | undefined;

  async function load(): Promise<void> {
    const mine = ++generation;
    pending.value = true;
    try {
      const found = await read();
      if (mine !== generation) return;
      shown.value = found;
      failure.value = null;
      hidden.value = false;
    } catch (error) {
      if (mine !== generation) return;
      failure.value = failureNotice(error, loadFailed);
      hidden.value = error instanceof ApiError && error.code === "file_hidden";
    }
    pending.value = false;
    answerRetry();
  }

  async function retry(): Promise<void> {
    retriedFrom = document.activeElement;
    retriedNotice = failure.value;
    if (shown.value === null) failure.value = null; // the waiting shows, and the alert comes again
    await load();
  }

  /** The reader's retry answered by the reading that counts - its own, or a later one that overtook
   * it: a failure is said again even in the same words, and the keyboard is left where it is. */
  function answerRetry(): void {
    if (retriedNotice === undefined) return;
    const before = retriedNotice;
    retriedNotice = undefined;
    if (failure.value && before && shown.value !== null) {
      failure.value = { ...failure.value, text: sayAnew(before.text, failure.value.text) };
    }
    if (failure.value) retriedFrom = undefined;
  }

  // after the render, before the focus rescue takes a focus the render dropped to the main region;
  // only where the focus still rests where the retry began, or nowhere
  watch(
    shown,
    () => {
      const from = retriedFrom;
      retriedFrom = undefined;
      if (from !== undefined && (document.activeElement === from || focusIsFree())) heading.value?.focus();
    },
    { flush: "post" },
  );

  return { shown, failure, hidden, pending, load, retry };
}
