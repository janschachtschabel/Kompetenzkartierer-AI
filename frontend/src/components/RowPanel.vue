<script setup lang="ts">
/**
 * The row chosen in a document's tree (plan M1 9.7/9.8, Paket 9c2 K2/K3/K6): where the tree is open, its form
 * (RowEditor) with its origin, status and anchors beside (RowDetail without fields); else the row as it reads,
 * with why it only reads - the document's state (`tree.closed`), or the caller's role. A change the closing
 * tree refused keeps its editor, the draft shown to copy, until another row is chosen - so does a draft the
 * tree, read anew, closed under. A row found gone is said in a status line the panel holds from the start,
 * the keyboard taken to the panel's heading, not lost with the editor. An anchor chosen in the source goes on to
 * the editor (`addAnchor`). Where the tree is open a node chosen offers a node or a statement to add under it
 * (RowActions); a row being added (`creating`, the view's) takes the place of the row chosen (RowCreator), the
 * keyboard at the heading as it begins, is cancelled or is added - not where another row chosen ends it. A row
 * taken away is said here, the keyboard at the heading: deleted, it leaves the address; rejected, changed
 * meanwhile or closed to change, the tree is read again.
 */
import { computed, nextTick, ref, useId, watch } from "vue";

import type { Form, Tree } from "@/api";
import RowActions from "@/components/RowActions.vue";
import RowCreator from "@/components/RowCreator.vue";
import RowDetail from "@/components/RowDetail.vue";
import RowEditor from "@/components/RowEditor.vue";
import type { Row, RowKey } from "@/documentTree";
import { t } from "@/i18n/de";
import { sayAnew } from "@/liveRegion";
import type { CreateTarget } from "@/rowCreate";
import { dropWords, type DropOutcome } from "@/rowDrop";

const props = withDefaults(defineProps<{ row: Row | null; tree: Tree; form: Form; creating?: CreateTarget | null }>(), {
  creating: null,
});
const emit = defineEmits<{
  show: [page: number];
  changed: [];
  gone: [];
  dirty: [open: boolean];
  create: [kind: "node" | "statement"];
  created: [key: RowKey];
  cancel: [];
}>();

const headingId = useId();
const headingRef = ref<HTMLElement | null>(null);
const editor = ref<InstanceType<typeof RowEditor> | null>(null);
const creator = ref<InstanceType<typeof RowCreator> | null>(null);
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
  if (props.creating) {
    return t(props.creating.kind === "node" ? "documents.tree.create.headingNode" : "documents.tree.create.headingStatement");
  }
  const row = props.row;
  if (!row) return t("documents.tree.detail.heading");
  if (row.kind === "statement") return t("documents.tree.detail.statement");
  const { code, original_title: title } = row.node.fields;
  const name = [code, title].filter((part) => typeof part === "string" && part).join(" ");
  return t("documents.tree.detail.node", { name: name || t("documents.tree.untitled") });
});

// the row just added, chosen as the tree is read again: the word that it was added stays for it
let added: RowKey | null = null;

watch(
  () => props.row?.key,
  (key) => {
    if (key !== refused.value) refused.value = null;
    if (key && key !== added) status.value = "";
    added = null;
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

// a row to add begins: the keyboard to the heading that says so, the button that began it gone or elsewhere
watch(
  () => props.creating,
  (now, was) => {
    if (now && !was) void nextTick(() => headingRef.value?.focus());
  },
);

function toHeading(): void {
  void nextTick(() => headingRef.value?.focus());
}

function created(key: RowKey): void {
  added = key;
  status.value = sayAnew(status.value, t("documents.tree.create.created"));
  toHeading();
  emit("created", key);
}

function cancel(): void {
  toHeading();
  emit("cancel");
}

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
  toHeading();
  emit("gone");
}

function dropped(done: Exclude<DropOutcome, { outcome: "failed" }>): void {
  if (done.outcome === "gone") return gone();
  status.value = sayAnew(status.value, dropWords(done));
  toHeading();
  // no more: out of the address, as a row found gone
  if (done.outcome === "dropped" || done.outcome === "deleted") emit("gone");
  else emit("changed");
}

/** An anchor chosen in the source, into the draft of the statement added or edited. */
function addAnchor(code: string): void {
  if (creator.value) creator.value.addAnchor(code);
  else editor.value?.addAnchor(code);
}

defineExpose({ addAnchor });
</script>

<template>
  <section class="row-panel" :aria-labelledby="headingId">
    <!-- tabindex -1: where the keyboard goes when the row it edited is found gone -->
    <h2 :id="headingId" ref="headingRef" tabindex="-1">
      <bdi>{{ heading }}</bdi>
    </h2>
    <p v-if="reason && !editing && !creating" class="row-panel__closed">{{ reason }}</p>
    <RowCreator
      v-if="creating"
      ref="creator"
      :key="JSON.stringify(creating)"
      :target="creating"
      :form="form"
      @created="created"
      @closed="emit('changed')"
      @gone="gone"
      @cancel="cancel"
      @dirty="dirty"
    />
    <template v-else-if="row">
      <RowActions
        v-if="tree.editable"
        :key="row.key"
        :row="row"
        @create="(kind) => emit('create', kind)"
        @dropped="dropped"
      />
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
