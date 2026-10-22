// The register as a page shows it: read from its start as far as the filter lets it through, a
// further page at a time, what did not come and how to try it again, and where the focus goes
// once the page shows what an action waited for. The page keeps its template, its filter and the
// address that holds it, and the jobs started on it (SourcesView.vue).
import { computed, ref, watch, type Ref } from "vue";

import { listSources, MAX_PAGE_SIZE, PAGE_SIZE, type SourceFilters, type SourcePage } from "@/api";
import { focusIsFree } from "@/focusRescue";
import { t } from "@/i18n/de";
import { sayAnew } from "@/liveRegion";
import { failureNotice, type Notice } from "@/notice";
import { askedOf, sameAsked, type RegisterFilters } from "@/registerFilters";

/** Where the focus goes once the page shows what an action waited for, and where that action began. */
interface FocusRequest {
  target: () => HTMLElement | null | undefined;
  from: Element | null;
}

/** The places of the page's own template the focus goes to. */
export interface RegisterPlaces {
  /** The register's heading: where the focus goes when a notice's retry button goes with the notice. */
  heading: () => HTMLElement | null;
  /** The table's row at `index`, as the page shows it then. */
  row: (index: number) => HTMLElement | undefined;
}

/** For a page's setup: the focus's watcher stops with the page. */
export function useRegisterPage(filters: Readonly<Ref<RegisterFilters>>, { heading, row }: RegisterPlaces) {
  const page = ref<SourcePage | null>(null);
  const loading = ref(true);
  const loadingMore = ref(false);
  /** The register did not load at all. */
  const failure = ref<Notice | null>(null);
  /** A reload or a further page did not, and what to try again; it stays until a try succeeds. */
  const partial = ref<{ notice: Notice; retry: () => void } | null>(null);
  /** What the shown page was read with: a further page asks with it, its empty state speaks of it. */
  const readWith = ref<SourceFilters>({});
  const pageFiltered = computed(() => Object.keys(readWith.value).length > 0);
  /** Said aloud when the filter lets nothing through: the table, and its count, went with it. */
  const filterNotice = ref("");
  // Each first page read counts: a further page asked for before it belongs to an older list.
  let generation = 0;
  let focusRequest: FocusRequest | null = null;
  // A failed reading took a shown page away, the table with it: the next page read brings it back.
  let dropped = false;

  // After the render, in the same flush - before the focus rescue moves a focus the render took to
  // the main region. Only where the focus still rests where the action began, or nowhere: whoever
  // went on to type elsewhere meanwhile keeps their place.
  watch(
    page,
    () => {
      const request = focusRequest;
      focusRequest = null;
      if (request && (document.activeElement === request.from || focusIsFree())) request.target()?.focus();
    },
    { flush: "post" },
  );

  /** The row after the entry `id`, as the page shows it then: an entry added above moves it down. */
  function rowAfter(id: string): HTMLElement | undefined {
    const index = page.value?.entries.findIndex((entry) => entry.id === id) ?? -1;
    return index < 0 ? undefined : row(index + 1);
  }

  /** The notice of a reload or a further page that did not come; the same one again is read out again. */
  function fallShort(notice: Notice, retry: () => void): void {
    partial.value = { notice: { ...notice, text: sayAnew(partial.value?.notice.text ?? "", notice.text) }, retry };
  }

  /**
   * The register read again from its start: as many entries as it shows, so a later page and the
   * focus in it stay, and `extra` more. `focus` is where the focus goes once it shows them - the
   * register's heading after the notice's retry button went with the notice. `from` is where the
   * action began - the press of "Weitere laden", when a further page turned into this reading.
   *
   * A page read with another filter than the one now set is no part of this filter's, whichever
   * reading asks - a new filter's, or a reload that overtakes it: the reading is one page, and
   * where it fails, that page goes rather than stand under this filter's controls.
   */
  async function load({
    extra = 0,
    focus,
    from = document.activeElement,
  }: { extra?: number; focus?: FocusRequest["target"]; from?: Element | null } = {}): Promise<void> {
    const mine = ++generation;
    const query = askedOf(filters.value);
    const kept = page.value && sameAsked(readWith.value, query) ? page.value : null;
    const limit = Math.min(MAX_PAGE_SIZE, Math.max(PAGE_SIZE, (kept?.entries.length ?? 0) + extra));
    loading.value = true;
    failure.value = null;
    try {
      const first = await listSources(query, { limit });
      if (mine !== generation) return;
      if (focus) focusRequest = { target: focus, from };
      const none = Object.keys(query).length > 0 && first.entries.length === 0;
      // the table comes back where the page showed none, or none was left of it, its count region
      // with it - and a region inserted with its words is often not read: the filter's status says them
      const back = (page.value?.entries.length === 0 || dropped) && first.entries.length > 0;
      dropped = false;
      page.value = first;
      readWith.value = query;
      partial.value = null;
      const count = t("sources.register.shown", { shown: first.entries.length, total: first.total });
      if (none) filterNotice.value = sayAnew(filterNotice.value, t("sources.filter.none"));
      else if (back) filterNotice.value = sayAnew(filterNotice.value, count);
      else filterNotice.value = "";
    } catch (error) {
      if (mine !== generation) return;
      if (kept) {
        fallShort(failureNotice(error, t("sources.register.reloadFailed")), () => void load({ focus: heading }));
      } else {
        // not where the first reading failed: the table that comes then comes for the first time
        if (page.value) dropped = true;
        page.value = null;
        partial.value = null; // a notice of the page that went, and its retry, went with it
        filterNotice.value = "";
        failure.value = failureNotice(error, t("sources.register.loadFailed"));
      }
    } finally {
      if (mine === generation) loading.value = false;
    }
  }

  async function more(): Promise<void> {
    const current = page.value;
    // the button stays focusable while busy; while the register is read again, a further page of it is no page
    if (!current || loadingMore.value || loading.value) return;
    const mine = generation;
    const from = document.activeElement;
    // the first entry not read before follows the last one shown, wherever that one is by then
    const lastShown = current.entries[current.entries.length - 1]?.id ?? "";
    const firstAddedRow = () => rowAfter(lastShown);
    loadingMore.value = true;
    try {
      const next = await listSources(readWith.value, { offset: current.entries.length });
      if (mine !== generation || page.value !== current) return;
      // newest first: an entry added meanwhile pushed one already shown onto this page, and itself
      // lies before the first - read the register from its start, a page more than it showed
      const shown = new Set(current.entries.map((entry) => entry.id));
      if (next.entries.some((entry) => shown.has(entry.id))) {
        return void (await load({ extra: PAGE_SIZE, focus: firstAddedRow, from }));
      }
      focusRequest = { target: firstAddedRow, from };
      page.value = { ...next, offset: 0, entries: [...current.entries, ...next.entries] };
      partial.value = null;
    } catch (error) {
      if (mine === generation) fallShort(failureNotice(error, t("sources.register.moreFailed")), () => void more());
    } finally {
      loadingMore.value = false;
    }
  }

  return { page, loading, loadingMore, failure, partial, readWith, pageFiltered, filterNotice, load, more };
}
