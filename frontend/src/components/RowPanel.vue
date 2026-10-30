<script setup lang="ts">
/**
 * The row chosen in a document's tree (plan M1 9.7/9.8, Paket 9c2 K2/K3/K6): where the tree is open, its form
 * (RowEditor) with its origin, status and anchors beside (RowDetail without fields); else the row as it reads,
 * with why it only reads - the document's state (`tree.closed`), or the caller's role. A change the closing
 * tree refused keeps its editor, the draft shown to copy, until another row is chosen - so does a draft the
 * tree, read anew, closed under. A row found gone is said in a status line the panel holds from the start,
 * the keyboard taken to the panel's heading, not lost with the editor. An anchor chosen in the source goes on to
 * the editor (`addAnchor`).
 */
import { computed, nextTick, ref, useId, watch } from "vue";

import type { Form, Tree } from "@/api";
import RowDetail from "@/components/RowDetail.vue";
import RowEditor from "@/components/RowEditor.vue";
import type { Row, RowKey } from "@/documentTree";
import { t } from "@/i18n/de";
import { sayAnew } from "@/liveRegion";

const props = defineProps<{ row: Row | null; tree: Tree; form: Form }>();
const emit = defineEmits<{ show: [page: number]; changed: []; gone: []; dirty: [open: boolean] }>();

const headingId = useId();
const headingRef = ref<HTMLElement | null>(null);
const editor = ref<InstanceType<typeof RowEditor> | null>(null);
// the row whose change the closing tree refused: its editor stays, the draft shown to copy
const refused = ref<RowKey | null>(null);
const status = ref("");
// a draft open in the editor
const draftOpen = ref(false);

const editing = computed(() => !!props.row && (props.tree.editable || refused.value === props.row.key));
const reason = computed(() => {
  if (props.tree.editable) return null;
  return props.tree.closed ? t(`documents.tree.closed.${props.tree.closed}`) : t("documents.tree.closed.noRole");
});

const heading = computed(() => {
  const row = props.row;
  if (!row) return t("documents.tree.detail.heading");
  if (row.kind === "statement") return t("documents.tree.detail.statement");
  const { code, original_title: title } = row.node.fields;
  const name = [code, title].filter((part) => typeof part === "string" && part).join(" ");
  return t("documents.tree.detail.node", { name: name || t("documents.tree.untitled") });
});

watch(
  () => props.row?.key,
  (key) => {
    if (key !== refused.value) refused.value = null;
    if (key) status.value = "";
  },
);
// The tree read anew closed under an open draft: its editor stays, the draft shown to copy. Closed to the
// caller's role alone, the row reads as it reads, with that reason
watch(
  () => props.tree,
  (now) => {
    if (now.closed && draftOpen.value && props.row) refused.value = props.row.key;
    else if (!now.closed && !now.editable) refused.value = null;
  },
);

function dirty(open: boolean): void {
  draftOpen.value = open;
  emit("dirty", open);
}

function closed(): void {
  refused.value = props.row?.key ?? null;
  emit("changed");
}

function gone(): void {
  status.value = sayAnew(status.value, t("documents.tree.gone"));
  void nextTick(() => headingRef.value?.focus());
  emit("gone");
}

/** An anchor chosen in the source, into the draft of the statement edited. */
function addAnchor(code: string): void {
  editor.value?.addAnchor(code);
}

defineExpose({ addAnchor });
</script>

<template>
  <section class="row-panel" :aria-labelledby="headingId">
    <!-- tabindex -1: where the keyboard goes when the row it edited is found gone -->
    <h2 :id="headingId" ref="headingRef" tabindex="-1">
      <bdi>{{ heading }}</bdi>
    </h2>
    <p v-if="reason && !editing" class="row-panel__closed">{{ reason }}</p>
    <template v-if="row">
      <RowEditor
        v-if="editing"
        ref="editor"
        :key="row.key"
        :row="row"
        :form="form"
        :closed-by="tree.editable ? null : tree.closed"
        @saved="emit('changed')"
        @closed="closed"
        @gone="gone"
        @dirty="dirty"
      />
      <RowDetail :row="row" :form="form" :fields="!editing" @show="(page) => emit('show', page)" />
    </template>
    <p v-else>{{ t("documents.tree.detail.none") }}</p>
    <!-- always in the page, so the first word is read out -->
    <p class="row-panel__status" role="status">{{ status }}</p>
  </section>
</template>

<style scoped>
.row-panel {
  display: grid;
  gap: var(--space-2);
  align-content: start;
}

.row-panel h2,
.row-panel__closed,
.row-panel__status {
  margin: 0;
}

.row-panel__closed {
  color: var(--text-muted);
}
</style>
