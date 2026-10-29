<script setup lang="ts">
/**
 * A document's tree (plan M1 9.7, Paket 9c J7): its nodes and, under each, its statements, as a WAI-ARIA tree
 * view laid out flat (treeRows.ts) - one tab stop, the keys of treeKeys.ts from the row focused (those with
 * Alt, Ctrl or Meta left to the browser), a row chosen with Enter, Space or a click; a node's
 * arrow, the mouse's alone, opens or closes it and leaves the keys at its row. Each row is named by one
 * sentence (treeRowWords.ts); the row chosen alone says it is. At first the top nodes are open, and the path
 * to the row chosen; the filter by review status opens the way to the rows of those statuses, a status line
 * says how many there are, and turning the filter off gives back the nodes open before it, and the way to a
 * row chosen meanwhile.
 */
import { computed, nextTick, ref, watch, type ComponentPublicInstance } from "vue";

import type { Form, Tree } from "@/api";
import AppIcon from "@/components/AppIcon.vue";
import EmptyState from "@/components/EmptyState.vue";
import TreeRow from "@/components/TreeRow.vue";
import TreeStatusFilter from "@/components/TreeStatusFilter.vue";
import type { Row, RowKey } from "@/documentTree";
import { t } from "@/i18n/de";
import { keyMove } from "@/treeKeys";
import { rowLabel, rowParts } from "@/treeRowWords";
import { ancestors, keptBy, matchesOf, visibleRows } from "@/treeRows";

const props = defineProps<{ rows: ReadonlyMap<RowKey, Row>; form: Form; counts: Tree["counts"] }>();
const selected = defineModel<RowKey | null>("selected", { default: null });

const expanded = ref(new Set<RowKey>());
const statuses = ref(new Set<string>());
// the row the keys are at: it holds the tab stop while it shows
const at = ref<RowKey | null>(null);
const elements = new Map<RowKey, HTMLElement>();
// what was open when the filter came on, given back when it goes off
let openBefore: Set<RowKey> | null = null;

const kept = computed(() => (statuses.value.size ? keptBy(props.rows, statuses.value) : null));
const visible = computed(() => visibleRows(props.rows, expanded.value, kept.value));
// each shown row with its words; a row whose place and state stay is not drawn again (v-memo below)
const shownRows = computed(() => visible.value.map((shown) => ({ shown, parts: rowParts(shown.row, props.form) })));
const tabStop = computed(() => {
  const shown = new Set(visible.value.map(({ row }) => row.key));
  for (const key of [at.value, selected.value]) if (key && shown.has(key)) return key;
  return visible.value[0]?.row.key ?? null;
});
const matching = computed(() => {
  if (!statuses.value.size) return "";
  const count = matchesOf(props.rows, statuses.value).length;
  return count ? t("documents.tree.matching", { count }) : t("documents.tree.noMatch");
});

function open(keys: Iterable<RowKey>): void {
  const next = new Set(expanded.value);
  for (const key of keys) next.add(key);
  // none newly open: the rows shown stay as they are
  if (next.size !== expanded.value.size) expanded.value = next;
}

function toggle(key: RowKey, on: boolean): void {
  const next = new Set(expanded.value);
  if (on) next.add(key);
  else next.delete(key);
  expanded.value = next;
}

// At first the top nodes are open; read again after an edit, the tree stays as it was opened
watch(
  () => props.rows,
  (rows, before) => {
    if (!before?.size) open([...rows.values()].filter((row) => row.parent === null).map((row) => row.key));
  },
  { immediate: true },
);
// A row chosen - here or from without, by the address - is where the keys are, its path open
watch(
  selected,
  (key) => {
    if (!key) return;
    at.value = key;
    open(ancestors(props.rows, key));
  },
  { immediate: true },
);
// The filter opens the way to its rows, also to those a new reading brings, and gives back what was open
watch([statuses, () => props.rows], ([on, rows], [was]) => {
  if (on.size && !was?.size) openBefore = new Set(expanded.value);
  if (on.size) open(matchesOf(rows, on).flatMap((key) => ancestors(rows, key)));
  else if (openBefore) {
    expanded.value = new Set([...openBefore, ...(selected.value ? ancestors(rows, selected.value) : [])]);
    openBefore = null;
  }
});

function remember(key: RowKey, element: Element | ComponentPublicInstance | null): void {
  if (element instanceof HTMLElement) elements.set(key, element);
  else elements.delete(key);
}

function focusRow(key: RowKey): void {
  at.value = key;
  void nextTick(() => elements.get(key)?.focus());
}

// The row a key was pressed on: the tab stop moves with a row chosen from without (the browser's back),
// the keys go on from where the reader is.
function keyedRow(target: EventTarget | null): RowKey | null {
  const item = target instanceof Element ? target.closest("[role=treeitem]") : null;
  return (item?.getAttribute("data-key") as RowKey | null | undefined) ?? null;
}

function onKey(event: KeyboardEvent): void {
  if (event.altKey || event.ctrlKey || event.metaKey) return;
  const here = keyedRow(event.target) ?? tabStop.value;
  if (here) at.value = here;
  const move = here ? keyMove(visible.value, here, event.key) : null;
  if (!move) return;
  event.preventDefault();
  if ("focus" in move) focusRow(move.focus);
  else if ("toggle" in move) toggle(move.toggle, move.open);
  else selected.value = move.select;
}

function choose(key: RowKey): void {
  at.value = key;
  selected.value = key;
}

function flip(key: RowKey, on: boolean): void {
  toggle(key, on);
  focusRow(key);
}
</script>

<template>
  <div class="tree">
    <TreeStatusFilter v-if="rows.size" v-model="statuses" :counts="counts" />
    <!-- always in the page, so the first count is read out -->
    <p class="tree__status" role="status">{{ matching }}</p>
    <EmptyState
      v-if="rows.size === 0"
      :level="3"
      :title="t('documents.tree.empty.title')"
      :body="t('documents.tree.empty.body')"
    />
    <ul v-else-if="visible.length" class="tree__rows" role="tree" :aria-label="t('documents.tree.label')" @keydown="onKey">
      <li
        v-for="item in shownRows"
        :key="item.shown.row.key"
        v-memo="[
          item.shown.row,
          item.shown.expandable,
          item.shown.expanded,
          item.shown.posinset,
          item.shown.setsize,
          form,
          item.shown.row.key === tabStop,
          item.shown.row.key === selected,
        ]"
        :ref="(element) => remember(item.shown.row.key, element as Element | null)"
        class="tree__row"
        :class="{ 'tree__row--selected': item.shown.row.key === selected }"
        :style="{ paddingInlineStart: `calc(${item.shown.level - 1} * var(--space-2))` }"
        role="treeitem"
        :data-key="item.shown.row.key"
        :aria-label="rowLabel(item.parts)"
        :aria-level="item.shown.level"
        :aria-posinset="item.shown.posinset"
        :aria-setsize="item.shown.setsize"
        :aria-expanded="item.shown.expandable ? item.shown.expanded : undefined"
        :aria-selected="item.shown.row.key === selected ? true : undefined"
        :tabindex="item.shown.row.key === tabStop ? 0 : -1"
        @click="choose(item.shown.row.key)"
        @focus="at = item.shown.row.key"
      >
        <!-- the mouse's alone: the keys open and close a node by the arrow keys, and its state is aria-expanded -->
        <span
          v-if="item.shown.expandable"
          class="tree__toggle"
          :class="{ 'tree__toggle--open': item.shown.expanded }"
          aria-hidden="true"
          @click.stop="flip(item.shown.row.key, !item.shown.expanded)"
        >
          <AppIcon name="chevron" />
        </span>
        <span v-else class="tree__spacer" aria-hidden="true"></span>
        <TreeRow :parts="item.parts" />
      </li>
    </ul>
  </div>
</template>

<style scoped>
.tree {
  display: grid;
  gap: var(--space-1);
}

.tree__status {
  margin: 0;
}

/* Empty, it takes no room - as a cell of the grid its gap would stand twice - but stays in the page, so its
   first word is read out. */
.tree__status:empty {
  position: absolute;
}

.tree__rows {
  list-style: none;
  margin: 0;
  padding: 0;
}

.tree__row {
  display: flex;
  align-items: flex-start;
  gap: var(--space-0);
  padding-block: var(--space-0);
  padding-inline-end: var(--space-1);
  border-inline-start: 3px solid transparent;
  border-radius: var(--radius-sm);
  cursor: pointer;
}

/* Not over the row chosen: its wash says it is chosen. */
.tree__row:not(.tree__row--selected):hover {
  background: var(--surface-subtle);
}

.tree__row:focus-visible {
  outline: 2px solid var(--focus);
  outline-offset: -2px;
}

/* Chosen: a bar and the wash, so it shows without colour too (aria-selected says it to a screen reader). */
.tree__row--selected {
  background: var(--accent-wash);
  border-inline-start-color: var(--accent);
}

.tree__toggle,
.tree__spacer {
  flex: none;
  inline-size: 1.5rem;
  block-size: 1.5rem;
}

.tree__toggle {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: var(--text-muted);
  transition: transform var(--dur-1) var(--ease);
}

.tree__toggle--open {
  transform: rotate(90deg);
}
</style>
