// What a document's tree page keeps in its address (plan M1 9.7, Paket 9c J2, L7): the row chosen and the page
// of the source (?zeile=node:<id>&seite=3), so back, forward and a reload keep them. A row chosen goes to the
// page of its first anchor - a row without anchors to the first page, not the page of the row before -; a
// page the address names otherwise than as a whole number is read as none.
import { computed, type Ref } from "vue";
import { useRoute, useRouter, type LocationQuery } from "vue-router";

import { PAGE_PARAM, pageOf } from "@/blockPages";
import { ROW_PARAM, type Row, type RowKey } from "@/documentTree";

function anchorsOf(row: Row | null): { page_start: number | null; blocks: string[] }[] {
  if (!row) return [];
  return row.kind === "node" ? row.node.anchors : row.statement.anchors;
}

function firstPage(row: Row | null): number | null {
  return anchorsOf(row).find((anchor) => anchor.page_start !== null)?.page_start ?? null;
}

/** Called in a page's setup: the route it is mounted at is its own. */
export function useTreeAddress(rows: Ref<Map<RowKey, Row>>) {
  const route = useRoute();
  const router = useRouter();

  // Only under the route the page was mounted at (as ConversionView): a leaving transition keeps it mounted
  // under the next page's address, whose query names no row or page of this one
  const ownRoute = route.name;
  const atOwnRoute = (): boolean => route.name === ownRoute;
  const query = computed<LocationQuery>((before) => (atOwnRoute() ? route.query : (before ?? {})));

  const selectedRow = computed<Row | null>(() => {
    const key = query.value[ROW_PARAM];
    return typeof key === "string" ? (rows.value.get(key as RowKey) ?? null) : null;
  });

  const selected = computed<RowKey | null>({
    get: () => selectedRow.value?.key ?? null,
    set: (key) => {
      const row = key ? (rows.value.get(key) ?? null) : null;
      const at = firstPage(row);
      void router.replace({
        query: { ...route.query, [ROW_PARAM]: key ?? undefined, [PAGE_PARAM]: at ? String(at) : undefined },
      });
    },
  });

  const page = computed(() => pageOf(query.value[PAGE_PARAM]) ?? firstPage(selectedRow.value) ?? 1);

  /** The blocks the chosen row's anchors name, each once. */
  const cited = computed(() => [...new Set(anchorsOf(selectedRow.value).flatMap((anchor) => anchor.blocks))]);

  function showPage(at: number): void {
    void router.replace({ query: { ...route.query, [PAGE_PARAM]: String(at) } });
  }

  /** The row chosen leaves the address, the page shown stays. */
  function leaveRow(): void {
    void router.replace({ query: { ...route.query, [ROW_PARAM]: undefined } });
  }

  return { selectedRow, selected, page, cited, showPage, leaveRow, atOwnRoute };
}
