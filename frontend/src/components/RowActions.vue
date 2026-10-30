<script setup lang="ts">
/**
 * The ways on from a row chosen in a tree the caller may change (plan M1 9.8, Paket 9c2b L4, L5, L9): under a
 * node, a node or a statement to add; the row taken away once asked (rowDrop.ts) - a node with what goes with
 * it counted, a statement rejected or deleted as the server decides. How it went is told to the panel, a
 * failure said here, where it was asked. Which row and whether the tree is open is the panel's.
 */
import { computed, ref } from "vue";

import AppIcon from "@/components/AppIcon.vue";
import ConfirmDialog from "@/components/ConfirmDialog.vue";
import NoticeText from "@/components/NoticeText.vue";
import type { Row } from "@/documentTree";
import { t } from "@/i18n/de";
import type { Notice } from "@/notice";
import { dropCounts, dropRow, type DropOutcome } from "@/rowDrop";

const props = defineProps<{ row: Row }>();
const emit = defineEmits<{
  create: [kind: "node" | "statement"];
  dropped: [done: Exclude<DropOutcome, { outcome: "failed" }>];
}>();

const asking = ref(false);
const busy = ref(false);
const problem = ref<Notice | null>(null);

const dropLabel = computed(() => t(props.row.kind === "node" ? "documents.tree.drop.node" : "documents.tree.drop.statement"));
const question = computed(() => {
  const row = props.row;
  if (row.kind === "statement") {
    return { title: t("documents.tree.drop.titleStatement"), message: t("documents.tree.drop.messageStatement") };
  }
  // the node itself not among those under it
  const { nodes, statements } = dropCounts(row.node);
  return { title: t("documents.tree.drop.titleNode"), message: t("documents.tree.drop.messageNode", { under: nodes - 1, statements }) };
});

async function drop(): Promise<void> {
  asking.value = false;
  busy.value = true;
  problem.value = null;
  const done = await dropRow(props.row);
  busy.value = false;
  if (done.outcome === "failed") problem.value = done.problem;
  else emit("dropped", done);
}
</script>

<template>
  <div class="row-actions">
    <template v-if="row.kind === 'node'">
      <button type="button" class="btn btn-sm secondary" @click="emit('create', 'node')">
        {{ t("documents.tree.create.child") }}
      </button>
      <button type="button" class="btn btn-sm secondary" @click="emit('create', 'statement')">
        {{ t("documents.tree.create.statement") }}
      </button>
    </template>
    <!-- aria-disabled, not disabled: the button keeps the keyboard while the row is taken away -->
    <button
      type="button"
      class="btn btn-sm secondary danger"
      :aria-disabled="busy || undefined"
      @click="busy || (asking = true)"
    >
      {{ dropLabel }}
    </button>
    <p v-if="problem" class="field__error row-actions__problem" role="alert">
      <AppIcon name="warning" /> <NoticeText :notice="problem" />
    </p>
    <ConfirmDialog
      v-if="asking"
      :title="question.title"
      :message="question.message"
      :confirm-label="dropLabel"
      @confirm="drop"
      @cancel="asking = false"
    />
  </div>
</template>

<style scoped>
.row-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-1);
}

.row-actions__problem {
  flex-basis: 100%;
  margin: 0;
}
</style>
