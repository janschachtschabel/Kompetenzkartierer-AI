<script setup lang="ts">
/**
 * The ways on from a row chosen in a tree the caller may change (plan M1 9.8, Paket 9c2b L4, L5, L9): under a
 * node, a node or a statement to add; the row taken away once asked (rowDrop.ts) - a node with what goes with
 * it counted, an editor's own statement deleted, a run's rejected and kept (Paket 9c2c M5: `by_hand`), none
 * offered for a run's statement rejected already, whose review status is set back instead. How it went is told
 * to the panel by a function (`onDropped`) with the row's key - heard even where another row was chosen
 * meanwhile -, a failure said here, where it was asked. Which row and whether the tree is open is the panel's.
 */
import { computed, ref } from "vue";

import AppIcon from "@/components/AppIcon.vue";
import ConfirmDialog from "@/components/ConfirmDialog.vue";
import NoticeText from "@/components/NoticeText.vue";
import type { Row, RowKey } from "@/documentTree";
import { t } from "@/i18n/de";
import type { Notice } from "@/notice";
import { dropCounts, dropRow, type DropOutcome } from "@/rowDrop";
import { rowStatus } from "@/rowReview";

const props = defineProps<{
  row: Row;
  /** How taking the row away went. A prop, not an event: these actions go with the row chosen. */
  onDropped?: (done: Exclude<DropOutcome, { outcome: "failed" }>, key: RowKey) => void;
}>();
const emit = defineEmits<{ create: [kind: "node" | "statement"] }>();

const asking = ref(false);
const busy = ref(false);
const problem = ref<Notice | null>(null);

// what taking the row away does: deletes a node or an editor's own statement, rejects a run's
const rejects = computed(() => props.row.kind === "statement" && !props.row.statement.by_hand);
// a run's statement rejected already: taking it away again would do nothing
const offered = computed(
  () => !(props.row.kind === "statement" && rejects.value && rowStatus(props.row) === "rejected"),
);
const dropLabel = computed(() => t(rejects.value ? "documents.tree.drop.reject" : "documents.tree.drop.node"));
const question = computed(() => {
  const row = props.row;
  if (row.kind === "statement") {
    return rejects.value
      ? { title: t("documents.tree.drop.titleReject"), message: t("documents.tree.drop.messageReject") }
      : { title: t("documents.tree.drop.titleDelete"), message: t("documents.tree.drop.messageDelete") };
  }
  // the node itself not among those under it
  const { nodes, statements } = dropCounts(row.node);
  return { title: t("documents.tree.drop.titleNode"), message: t("documents.tree.drop.messageNode", { under: nodes - 1, statements }) };
});

async function drop(): Promise<void> {
  const { key } = props.row;
  asking.value = false;
  busy.value = true;
  problem.value = null;
  const done = await dropRow(props.row);
  busy.value = false;
  if (done.outcome === "failed") problem.value = done.problem;
  else props.onDropped?.(done, key);
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
      v-if="offered"
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
