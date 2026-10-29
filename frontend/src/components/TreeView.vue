<script setup lang="ts">
/**
 * A document's tree (plan M1 9.7, Paket 9c J7): its nodes and, under each, its statements, as a WAI-ARIA tree
 * view laid out flat (treeRows.ts) - one tab stop, the keys of treeKeys.ts, a row chosen with Enter, Space or
 * a click, a node opened or closed by its button too. At first the top nodes are open, and the path to the
 * row chosen; the filter by review status opens the path to what it keeps, and a status line says how many
 * rows are of those statuses.
 */
import { computed, nextTick, ref, useId, watch, type ComponentPublicInstance } from "vue";

import type { Form, Tree } from "@/api";
import AppIcon from "@/components/AppIcon.vue";
import EmptyState from "@/components/EmptyState.vue";
import TreeRow from "@/components/TreeRow.vue";
import TreeStatusFilter from "@/components/TreeStatusFilter.vue";
import type { Row, RowKey } from "@/documentTree";
import { t } from "@/i18n/de";
import { keyMove } from "@/treeKeys";
import { ancestors, keptBy, visibleRows } from "@/treeRows";

const props = defineProps<{ rows: ReadonlyMap<RowKey, Row>; form: Form; counts: Tree["counts"] }>();
const selected = defineModel<RowKey | null>("selected", { default: null });

const base = useId();
const expanded = ref(new Set<RowKey>());
const statuses = ref(new Set<string>());
// the row the keys are at: it holds the tab stop while it shows
const at = ref<RowKey | null>(null);
const elements = new Map<RowKey, HTMLElement>();

const kept = computed(() => (statuses.value.size ? keptBy(props.rows, statuses.value) : null));
const visible = computed(() => visibleRows(props.rows, expanded.value, kept.value));
const tabStop = computed(() => {
  const shown = new Set(visible.value.map(({ row }) => row.key));
  for (const key of [at.value, selected.value]) if (key && shown.has(key)) return key;
  return visible.value[0]?.row.key ?? null;
});
const matching = computed(() => {
  if (!statuses.value.size) return "";
  let count = 0;
  for (const row of props.rows.values()) {
    if (statuses.value.has((row.kind === "node" ? row.node : row.statement).review_status)) count++;
  }
  return count ? t("documents.tree.matching", { count }) : t("documents.tree.noMatch");
});

function open(keys: Iterable<RowKey>): void {
  const next = new Set(expanded.value);
  for (const key of keys) next.add(key);
  expanded.value = next;
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
watch(
  selected,
  (key) => {
    if (key) open(ancestors(props.rows, key));
  },
  { immediate: true },
);
watch(statuses, (on) => {
  if (on.size) open(keptBy(props.rows, on));
});

function labelId(key: RowKey): string {
  return `${base}-${key.replace(/[^\w-]/g, "-")}`;
}

function remember(key: RowKey, element: Element | ComponentPublicInstance | null): void {
  if (element instanceof HTMLElement) elements.set(key, element);
  else elements.delete(key);
}

function focusRow(key: RowKey): void {
  at.value = key;
  void nextTick(() => elements.get(key)?.focus());
}

function onKey(event: KeyboardEvent): void {
  const here = tabStop.value;
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
</script>

<template>
  <div class="tree">
    <TreeStatusFilter v-model="statuses" :counts="counts" />
    <p class="tree__status" role="status">{{ matching }}</p>
    <EmptyState
      v-if="rows.size === 0"
      :level="3"
      :title="t('documents.tree.empty.title')"
      :body="t('documents.tree.empty.body')"
    />
    <ul v-else class="tree__rows" role="tree" :aria-label="t('documents.tree.label')" @keydown="onKey">
      <li
        v-for="shown in visible"
        :key="shown.row.key"
        :ref="(element) => remember(shown.row.key, element as Element | null)"
        class="tree__row"
        :class="{ 'tree__row--selected': shown.row.key === selected }"
        :style="{ paddingInlineStart: `${(shown.level - 1) * 1.25}rem` }"
        role="treeitem"
        :data-key="shown.row.key"
        :aria-level="shown.level"
        :aria-posinset="shown.posinset"
        :aria-setsize="shown.setsize"
        :aria-expanded="shown.expandable ? shown.expanded : undefined"
        :aria-selected="shown.row.key === selected ? 'true' : 'false'"
        :aria-labelledby="labelId(shown.row.key)"
        :tabindex="shown.row.key === tabStop ? 0 : -1"
        @click="choose(shown.row.key)"
        @focus="at = shown.row.key"
      >
        <button
          v-if="shown.expandable"
          type="button"
          class="tree__toggle"
          :class="{ 'tree__toggle--open': shown.expanded }"
          tabindex="-1"
          :aria-label="shown.expanded ? t('documents.tree.close') : t('documents.tree.open')"
          @click.stop="toggle(shown.row.key, !shown.expanded)"
        >
          <AppIcon name="chevron" />
        </button>
        <span v-else class="tree__spacer" aria-hidden="true"></span>
        <TreeRow :id="labelId(shown.row.key)" :row="shown.row" :form="form" />
      </li>
    </ul>
  </div>
</template>

<style scoped>
.tree {
  display: grid;
  gap: var(--space-1);
}

.tree__status:empty {
  display: none;
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

.tree__row:hover {
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
  padding: 0;
  border: none;
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
  transition: transform var(--dur-1) var(--ease);
}

.tree__toggle--open {
  transform: rotate(90deg);
}

@media (prefers-reduced-motion: reduce) {
  .tree__toggle {
    transition: none;
  }
}
</style>
