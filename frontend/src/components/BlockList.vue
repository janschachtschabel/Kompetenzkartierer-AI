<script setup lang="ts">
/**
 * One page's blocks in reading order, each with the ID a quote cites, what it is where it is more
 * than text - a table, a running head or foot - and whether its type is bold or italic, which
 * tells a heading from the text under it. The text keeps the conversion's line breaks. Running
 * heads and feet are quieter than the text, as on paper; they are kept, not dropped, since a
 * page number in them is what a reader cites.
 */
import type { Block } from "@/api";
import BlockTable from "@/components/BlockTable.vue";
import { messages, t } from "@/i18n/de";
import { word } from "@/registerWords";

defineProps<{ blocks: Block[] }>();
</script>

<template>
  <ol class="blocks">
    <li v-for="item in blocks" :key="item.id" class="block" :class="`block--${item.kind}`">
      <p class="block__meta">
        <code class="block__id">{{ item.id }}</code>
        <span v-if="item.kind !== 'text'" class="block__kind">{{ word(messages.conversionPage.kind, item.kind) }}</span>
        <span v-if="item.bold">{{ t("conversionPage.bold") }}</span>
        <span v-if="item.italic">{{ t("conversionPage.italic") }}</span>
      </p>
      <BlockTable v-if="item.kind === 'table' && item.cells.length" :block="item" />
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
