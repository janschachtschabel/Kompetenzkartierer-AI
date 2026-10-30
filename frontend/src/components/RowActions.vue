<script setup lang="ts">
/**
 * The ways on from a row chosen in a tree the caller may change (plan M1 9.8, Paket 9c2b L4, L9): under a node,
 * a node or a statement to add. Which row and whether the tree is open is the panel's.
 */
import type { Row } from "@/documentTree";
import { t } from "@/i18n/de";

defineProps<{ row: Row }>();
const emit = defineEmits<{ create: [kind: "node" | "statement"] }>();
</script>

<template>
  <div v-if="row.kind === 'node'" class="row-actions">
    <button type="button" class="btn btn-sm secondary" @click="emit('create', 'node')">
      {{ t("documents.tree.create.child") }}
    </button>
    <button type="button" class="btn btn-sm secondary" @click="emit('create', 'statement')">
      {{ t("documents.tree.create.statement") }}
    </button>
  </div>
</template>

<style scoped>
.row-actions {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-1);
}
</style>
