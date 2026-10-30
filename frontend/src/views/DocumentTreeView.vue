<script setup lang="ts">
/**
 * A document's tree page (plan M1 9.7-9.9, Paket 9c J2): its nodes and statements as a tree (TreeView), the
 * row chosen - in its form where the tree is open, as it reads where not (RowPanel) - and under it the source:
 * a page of the conversion the document was read off, the blocks the row's anchors name marked (SourcePane).
 * The row chosen and the page of the source stand in the address (?zeile=node:<id>&seite=3), so back, forward
 * and a reload keep them; a row chosen goes to the page of its first anchor, the keyboard staying in the tree,
 * and an anchor's page takes the keyboard along to the source. A saved change reads the tree again, the row
 * staying chosen; a row found gone leaves the address. Where a later reading fails the tree stays, the
 * failure said above it (Paket 9c2 K12). A draft not yet saved is asked about before another row or another
 * page takes its place, the browser asking before the tab closes (K8); another page of the source keeps it.
 * A statement chosen in a tree open to the caller has its anchor chosen in the source, which goes to its
 * draft (Paket 9c2b L3, L9). There a node is added at the tree's top (TreeTools), or a node or a statement under
 * a node chosen, in the panel (L4); added, the tree is read again and the new row chosen; another row chosen lets
 * it go, a draft with entries asked about first (L10). There, too, the tree is checked again, its job followed
 * (TreeTools, Paket 9c2c M6), and an editor sets a row's review status in the panel (M2). Wide, the tree and the
 * side stand side by side.
 */
import { computed, nextTick, onMounted, ref, toRef, watch } from "vue";
import { RouterLink, useRoute } from "vue-router";

import ConfirmDialog from "@/components/ConfirmDialog.vue";
import EmptyState from "@/components/EmptyState.vue";
import ErrorState from "@/components/ErrorState.vue";
import LoadingState from "@/components/LoadingState.vue";
import PartialState from "@/components/PartialState.vue";
import RowPanel from "@/components/RowPanel.vue";
import SourcePane from "@/components/SourcePane.vue";
import TreeTools from "@/components/TreeTools.vue";
import TreeView from "@/components/TreeView.vue";
import { ROW_PARAM, useDocumentTree } from "@/documentTree";
import { focusIsFree } from "@/focusRescue";
import { t } from "@/i18n/de";
import { useLeaveGuard } from "@/leaveGuard";
import { pageTitle } from "@/pageTitle";
import { useTreeAdding } from "@/treeAdding";
import { useTreeAddress } from "@/treeAddress";

const props = defineProps<{ id: string }>();
const route = useRoute();
const { document: document_, tree, form, rows, loading, missing, hidden, failure, load } = useDocumentTree(
  toRef(props, "id"),
);
const { selectedRow, selected, page, cited, showPage, leaveRow, atOwnRoute } = useTreeAddress(rows);
// a change not yet saved in the row's form: another row or page takes it along, another page of the source not
const draftOpen = ref(false);
const { leaving, answer } = useLeaveGuard(draftOpen, {
  goesWith: (to, from) => to.path !== from.path || to.query[ROW_PARAM] !== from.query[ROW_PARAM],
});

const heading = computed(() =>
  document_.value
    ? t("documents.tree.heading", { title: document_.value.title || t("documents.untitled") })
    : t("app.titles.documentTree"),
);

const source = ref<InstanceType<typeof SourcePane> | null>(null);
const panel = ref<InstanceType<typeof RowPanel> | null>(null);

const { creating, pending, picking, discardWords: discard, createAtTop, create, answer: answerPending, created, cancel } =
  useTreeAdding({
    documentId: toRef(props, "id"),
    tree,
    selectedRow,
    selected,
    draftOpen,
    load,
    atOwnRoute,
  });

// an anchor's page is there to be read: the keyboard goes along to it
function showAnchor(at: number): void {
  showPage(at);
  source.value?.focus();
}

const treeHeading = ref<HTMLElement | null>(null);

// A reading again the reader asked for: its button goes with the notice, the keyboard to the tree's heading
// where it still rests on the button or nowhere, once the tree came (as sectionReading.ts does for a
// section); failed again, or overtaken by a later reading, the keyboard is left to that
async function readAgain(): Promise<void> {
  const from = document.activeElement;
  await load();
  await nextTick();
  if (loading.value || failure.value) return;
  if (document.activeElement === from || focusIsFree()) treeHeading.value?.focus();
}

// the row is no more, its draft with it: out of the address, the tree read anew
function rowGone(): void {
  draftOpen.value = false;
  leaveRow();
  void load();
}

onMounted(() => void load());
watch(
  () => props.id,
  () => void load(),
);
// The tab names the document once it is known; until then the router's name for the page stands. The
// router names the page alone on each move, the query's too (router.afterEach): named again after it.
watch([heading, () => route.fullPath], ([name]) => {
  if (atOwnRoute() && document_.value) document.title = pageTitle(name);
});
</script>

<template>
  <div class="page document-tree">
    <p class="document-tree__back">
      <RouterLink :to="{ name: 'document', params: { id } }">{{ t("documents.tree.back") }}</RouterLink>
    </p>
    <h1>
      <bdi>{{ heading }}</bdi>
    </h1>

    <LoadingState v-if="loading && !tree" />
    <EmptyState
      v-else-if="missing"
      :level="2"
      :title="t('documents.page.notFoundTitle')"
      :body="t('documents.page.notFoundBody')"
    />
    <!-- no retry: none changes whose content it is -->
    <EmptyState
      v-else-if="hidden"
      :level="2"
      :title="t('conversionPage.hiddenTitle')"
      :body="t('refusals.file_hidden')"
    />
    <ErrorState
      v-else-if="failure && !tree"
      :message="failure.text"
      :reason="failure.reason"
      :explanation="failure.explanation"
      @retry="load()"
    />
    <template v-else-if="tree && form">
      <PartialState class="document-tree__partial" :notice="failure" retry @retry="readAgain" />
      <div class="document-tree__panes">
        <section class="document-tree__tree" aria-labelledby="document-tree-rows">
          <!-- tabindex -1: where the keyboard goes after a reading again -->
          <h2 id="document-tree-rows" ref="treeHeading" tabindex="-1">{{ t("documents.tree.treeHeading") }}</h2>
          <!-- keyed by the document: a check of the one before is not followed here -->
          <TreeTools :key="id" :tree="tree" :document-id="id" @create-top="createAtTop" @changed="load()" />
          <TreeView v-model:selected="selected" :rows="rows" :form="form" :counts="tree.counts" />
        </section>
        <div class="document-tree__side">
          <RowPanel
            ref="panel"
            :row="selectedRow"
            :tree="tree"
            :form="form"
            :document-id="id"
            :creating="creating"
            @show="showAnchor"
            @changed="load()"
            @gone="rowGone"
            @dirty="(open) => (draftOpen = open)"
            @create="create"
            @created="created"
            @cancel="cancel"
          />
          <SourcePane
            ref="source"
            :document-id="id"
            :page="page"
            :cited="cited"
            :picking="picking"
            :take-anchor="(code) => panel?.addAnchor(code) ?? 'refused'"
            @go="showPage"
          />
        </div>
      </div>
    </template>
    <ConfirmDialog
      v-if="leaving || pending"
      :title="discard.title"
      :message="discard.message"
      :confirm-label="discard.confirm"
      :cancel-label="discard.cancel"
      @confirm="leaving ? answer(true) : answerPending(true)"
      @cancel="leaving ? answer(false) : answerPending(false)"
    />
  </div>
</template>

<style scoped>
.document-tree__back {
  margin: 0;
}

.document-tree__panes {
  display: grid;
  gap: var(--space-3);
}

.document-tree__tree,
.document-tree__side {
  display: grid;
  gap: var(--space-2);
  align-content: start;
  min-width: 0;
}

/* Wide, the tree beside what it chose; narrow, one under the other in that order. */
@media (min-width: 60rem) {
  .document-tree__panes {
    grid-template-columns: minmax(18rem, 2fr) minmax(0, 3fr);
  }
}
</style>
