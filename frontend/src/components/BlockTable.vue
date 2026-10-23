<script setup lang="ts">
/**
 * A table block as a table: its rows as the conversion read them, a header row's cells heading
 * their columns, and each cell with its ID - `T4:r3c2`, the table's number, its row and column -
 * since a quote cites a cell by it. The ID is shown and read with the cell, not hidden in a
 * tooltip: whoever cites needs it, by eye or by ear. A cell the table carried over from the next
 * page says where it stands; one the file left empty keeps its column. A table run on from an
 * earlier page shows its cells on this one, and says it is a continuation.
 */
import { computed, useId } from "vue";

import type { BlockCell } from "@/api";
import { t } from "@/i18n/de";

const props = defineProps<{
  cells: BlockCell[];
  /** The page shown: a cell standing on another says which. */
  page: number;
  continued?: boolean;
}>();
const captionId = useId();

interface Row {
  number: number;
  /** A row of header cells alone heads the columns under it. */
  heading: boolean;
  /** Its cells by column, from the first; null where the file has none. */
  cells: (BlockCell | null)[];
}

const rows = computed<Row[]>(() => {
  const columns = Math.max(0, ...props.cells.map((cell) => cell.column));
  const byRow = new Map<number, BlockCell[]>();
  for (const cell of props.cells) byRow.set(cell.row, [...(byRow.get(cell.row) ?? []), cell]);
  return [...byRow.entries()]
    .sort(([a], [b]) => a - b)
    .map(([number, cells]) => ({
      number,
      heading: cells.every((cell) => cell.header),
      cells: Array.from({ length: columns }, (_, index) => cells.find((cell) => cell.column === index + 1) ?? null),
    }));
});

/** The table's number, which its cells' IDs begin with. */
const number = computed(() => /^T(\d+):/.exec(props.cells[0]?.id ?? "")?.[1] ?? "");
const caption = computed(() =>
  t(props.continued ? "conversionPage.table.continuedCaption" : "conversionPage.table.caption", { table: number.value }),
);

function scopeOf(row: Row): "col" | "row" {
  return row.heading ? "col" : "row";
}
</script>

<template>
  <!-- Focusable and named by its caption: a wide table scrolls sideways, and a keyboard can only
       scroll what it reaches; one name, so it is not read twice -->
  <div class="block-table" tabindex="0" role="region" :aria-labelledby="captionId">
    <table class="block-table__table">
      <caption :id="captionId" class="block-table__caption">{{ caption }}</caption>
      <tbody>
        <tr v-for="row in rows" :key="row.number">
          <template v-for="(cell, index) in row.cells" :key="cell?.id ?? `${row.number}-${index}`">
            <component :is="cell?.header ? 'th' : 'td'" v-if="cell" :scope="cell.header ? scopeOf(row) : undefined">
              <code class="cell__id">{{ cell.id }}</code>
              <span class="cell__text" dir="auto">{{ cell.text }}</span>
              <span v-if="cell.page !== page" class="cell__page">{{ t("conversionPage.table.onPage", { page: cell.page }) }}</span>
            </component>
            <td v-else></td>
          </template>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<style scoped>
.block-table {
  overflow-x: auto;
}

.block-table__table {
  border-collapse: collapse;
  font-size: var(--step--1);
}

.block-table__caption {
  text-align: start;
  font-size: var(--step--2);
  color: var(--text-muted);
  padding-block-end: var(--space-0);
}

.block-table__table th,
.block-table__table td {
  padding: var(--space-0) var(--space-1);
  border: 1px solid var(--border);
  text-align: start;
  vertical-align: top;
}

.block-table__table th {
  background: var(--surface-subtle);
  font-weight: 600;
}

.cell__id,
.cell__page {
  display: block;
  color: var(--text-muted);
  font-size: var(--step--2);
}

.cell__id {
  font-family: var(--font-mono);
  font-weight: 400;
}

/* The conversion's line breaks stay; a long word breaks rather than widening every column. */
.cell__text {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
</style>
