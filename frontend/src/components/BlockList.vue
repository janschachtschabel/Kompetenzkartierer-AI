<script setup lang="ts">
/**
 * One page's blocks in reading order, each with the ID a quote cites, what it is where it is more
 * than text - a table, a running head or foot - and whether its type is bold or italic, which
 * tells a heading from the text under it. The text keeps the conversion's line breaks. Running
 * heads and feet are quieter than the text, as on paper; they are kept, not dropped, since a
 * page number in them is what a reader cites. A table run on from an earlier page comes first,
 * as on paper, under its block's ID, with the way to the page it begins on - the rest of the address
 * kept, as the document's tree keeps the row chosen there. The blocks `cited` - those a row's anchors
 * name (SourcePane) - are marked by the word "Beleg" and a stronger edge, not by a colour alone. While an
 * anchor is chosen (`picking`, Paket 9c2b L3) each block is a toggle named by its id, those `picked` pressed,
 * ticked and edged; which are chosen is the caller's, told each `toggle`.
 */
import { RouterLink, useRoute } from "vue-router";

import type { Block, ContinuedTable } from "@/api";
import { PAGE_PARAM } from "@/blockPages";
import BlockTable from "@/components/BlockTable.vue";
import BlockToggle from "@/components/BlockToggle.vue";
import { messages, t } from "@/i18n/de";
import { word } from "@/registerWords";

withDefaults(
  defineProps<{
    blocks: Block[];
    continued: ContinuedTable[];
    page: number;
    cited?: ReadonlySet<string>;
    picking?: boolean;
    picked?: ReadonlySet<string>;
  }>(),
  { cited: () => new Set<string>(), picking: false, picked: () => new Set<string>() },
);
const emit = defineEmits<{ toggle: [id: string] }>();
const route = useRoute();
</script>

<template>
  <ol class="blocks">
    <li
      v-for="item in continued"
      :key="`continued-${item.id}`"
      class="block block--table"
      :class="{ 'block--cited': cited.has(item.id), 'block--picked': picked.has(item.id) }"
      data-test="continued"
    >
      <p class="block__meta">
        <code class="block__id">{{ item.id }}</code>
        <span v-if="cited.has(item.id)" class="block__cited">{{ t("conversionPage.cited") }}</span>
        <span class="block__kind">{{ t("conversionPage.kind.table") }}</span>
        <span>{{ t("conversionPage.continued", { page: item.page }) }}</span>
        <RouterLink :to="{ query: { ...route.query, [PAGE_PARAM]: String(item.page) } }" replace>
          {{ t("conversionPage.tableStart", { page: item.page }) }}
        </RouterLink>
        <BlockToggle v-if="picking" :id="item.id" :pressed="picked.has(item.id)" @toggle="emit('toggle', item.id)" />
      </p>
      <BlockTable :cells="item.cells" :page="page" continued />
    </li>
    <li
      v-for="item in blocks"
      :key="item.id"
      class="block"
      :class="[`block--${item.kind}`, { 'block--cited': cited.has(item.id), 'block--picked': picked.has(item.id) }]"
    >
      <p class="block__meta">
        <code class="block__id">{{ item.id }}</code>
        <span v-if="cited.has(item.id)" class="block__cited">{{ t("conversionPage.cited") }}</span>
        <span v-if="item.kind !== 'text'" class="block__kind">{{ word(messages.conversionPage.kind, item.kind) }}</span>
        <span v-if="item.bold">{{ t("conversionPage.bold") }}</span>
        <span v-if="item.italic">{{ t("conversionPage.italic") }}</span>
        <BlockToggle v-if="picking" :id="item.id" :pressed="picked.has(item.id)" @toggle="emit('toggle', item.id)" />
      </p>
      <BlockTable v-if="item.kind === 'table' && item.cells.length" :cells="item.cells" :page="item.page" />
      <!-- on one line: the text keeps its white space, the template's would show -->
      <p v-else class="block__text" :class="{ 'block__text--bold': item.bold, 'block__text--italic': item.italic }" dir="auto">{{ item.text }}</p>
    </li>
  </ol>
</template>

<style scoped>
.blocks {
  display: grid;
  gap: var(--space-1);
  margin: 0;
  padding: 0;
  list-style: none;
}

.block {
  padding: var(--space-1) var(--space-2);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--surface);
}

/* Quieter than the text, by its tint and a dashed edge, and still clear of 4.5:1 (muted text on
   the subtle surface, tests/contrast.test.ts); the word in its line says what it is. */
.block--page_header,
.block--page_footer {
  border-style: dashed;
  background: var(--surface-subtle);
  color: var(--text-muted);
}

.block__meta {
  display: flex;
  flex-wrap: wrap;
  gap: 0 var(--space-1);
  margin: 0 0 var(--space-0);
  color: var(--text-muted);
  font-size: var(--step--2);
}

.block__id {
  font-family: var(--font-mono);
  color: var(--text);
}

/* A block the row chosen names: its word in the line, and a thick edge on the side the text begins. */
.block--cited {
  border-inline-start: 4px solid var(--accent);
}

.block__cited {
  font-weight: 700;
  color: var(--accent);
}

/* A block chosen for an anchor: an edge all round, beside its toggle's tick and wash. */
.block--picked {
  outline: 2px dashed var(--accent);
  outline-offset: 2px;
}

.block__kind {
  font-weight: 600;
}

.block__text {
  margin: 0;
  max-width: var(--reading-width);
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.block__text--bold {
  font-weight: 700;
}

.block__text--italic {
  font-style: italic;
}
</style>
