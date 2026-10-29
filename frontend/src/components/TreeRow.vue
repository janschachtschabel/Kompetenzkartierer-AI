<script setup lang="ts">
/**
 * One row of a document's tree as it shows (TreeView, plan M1 9.7): its parts (treeRowWords.ts) - the review
 * status a word beside its tone, never the tone alone. The row's name, the parts as one sentence, the tree
 * gives the row itself.
 */
import { t } from "@/i18n/de";
import type { RowParts } from "@/treeRowWords";

defineProps<{ parts: RowParts }>();
</script>

<template>
  <span class="tree-row">
    <span v-if="parts.code" class="tree-row__code">{{ parts.code }}</span>
    <bdi :class="parts.kind === 'node' ? 'tree-row__title' : 'tree-row__wording'">{{ parts.text }}</bdi>
    <span v-if="parts.type" class="tree-row__kind">{{ parts.type }}</span>
    <span class="status-badge" :class="parts.tone">{{ parts.status }}</span>
    <span v-if="parts.findings" class="tree-row__findings">
      {{ t("documents.tree.findings", { count: parts.findings }) }}
    </span>
  </span>
</template>

<style scoped>
.tree-row {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: var(--space-0) var(--space-1);
  min-width: 0;
}

.tree-row__code {
  font-family: var(--font-mono);
  font-size: var(--step--1);
}

.tree-row__title {
  font-weight: 600;
}

/* Two lines of a statement's wording in the tree; the detail shows it whole, and the row's name says it whole. */
.tree-row__wording {
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  overflow: hidden;
  flex: 1 1 18rem;
}

.tree-row__kind,
.tree-row__findings {
  color: var(--text-muted);
  font-size: var(--step--1);
}
</style>
