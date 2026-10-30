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
 * Wide, the tree and the side stand side by side.
 */
import { computed, onMounted, ref, toRef, watch } from "vue";
import { RouterLink, useRoute, useRouter, type LocationQuery } from "vue-router";

import { PAGE_PARAM, pageOf } from "@/blockPages";
import ConfirmDialog from "@/components/ConfirmDialog.vue";
import EmptyState from "@/components/EmptyState.vue";
import ErrorState from "@/components/ErrorState.vue";
import LoadingState from "@/components/LoadingState.vue";
import PartialState from "@/components/PartialState.vue";
import RowPanel from "@/components/RowPanel.vue";
import SourcePane from "@/components/SourcePane.vue";
import TreeView from "@/components/TreeView.vue";
import { ROW_PARAM, useDocumentTree, type Row, type RowKey } from "@/documentTree";
import { t } from "@/i18n/de";
import { useLeaveGuard } from "@/leaveGuard";
import { pageTitle } from "@/pageTitle";

const props = defineProps<{ id: string }>();
const route = useRoute();
const router = useRouter();
const { document: document_, tree, form, rows, loading, missing, hidden, failure, load } = useDocumentTree(
  toRef(props, "id"),
);
// a change not yet saved in the row's form: another row or page takes it along, another page of the source not
const draftOpen = ref(false);
const { leaving, answer } = useLeaveGuard(draftOpen, {
  goesWith: (to, from) => to.path !== from.path || to.query[ROW_PARAM] !== from.query[ROW_PARAM],
});

function anchorsOf(row: Row | null): { page_start: number | null; blocks: string[] }[] {
  if (!row) return [];
  return row.kind === "node" ? row.node.anchors : row.statement.anchors;
}

function firstPage(row: Row | null): number | null {
  return anchorsOf(row).find((anchor) => anchor.page_start !== null)?.page_start ?? null;
}

// Only under the route the page was mounted at (as ConversionView): a leaving transition keeps it mounted
// under the next page's address, whose query names no row or page of this one
const ownRoute = route.name;
const query = computed<LocationQuery>((before) => (route.name === ownRoute ? route.query : (before ?? {})));

const selectedRow = computed<Row | null>(() => {
  const key = query.value[ROW_PARAM];
  return typeof key === "string" ? (rows.value.get(key as RowKey) ?? null) : null;
});

const selected = computed<RowKey | null>({
  get: () => selectedRow.value?.key ?? null,
  set: (key) => {
    const row = key ? (rows.value.get(key) ?? null) : null;
    const at = firstPage(row);
    // a row without anchors shows the first page, not the page of the row before
    void router.replace({
      query: { ...route.query, [ROW_PARAM]: key ?? undefined, [PAGE_PARAM]: at ? String(at) : undefined },
    });
  },
});

const page = computed(() => pageOf(query.value[PAGE_PARAM]) ?? firstPage(selectedRow.value) ?? 1);

const cited = computed(() => [...new Set(anchorsOf(selectedRow.value).flatMap((anchor) => anchor.blocks))]);

const heading = computed(() =>
  document_.value
    ? t("documents.tree.heading", { title: document_.value.title || t("documents.untitled") })
    : t("app.titles.documentTree"),
);

function showPage(at: number): void {
  void router.replace({ query: { ...route.query, [PAGE_PARAM]: String(at) } });
}

const source = ref<InstanceType<typeof SourcePane> | null>(null);

// an anchor's page is there to be read: the keyboard goes along to it
function showAnchor(at: number): void {
  showPage(at);
  source.value?.focus();
}

// the row is no more, its draft with it: out of the address, the tree read anew
function rowGone(): void {
  draftOpen.value = false;
  void router.replace({ query: { ...route.query, [ROW_PARAM]: undefined } });
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
  if (route.name === ownRoute && document_.value) document.title = pageTitle(name);
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
      <PartialState class="document-tree__partial" :notice="failure" retry @retry="load()" />
      <div class="document-tree__panes">
        <section class="document-tree__tree" aria-labelledby="document-tree-rows">
          <h2 id="document-tree-rows">{{ t("documents.tree.treeHeading") }}</h2>
          <TreeView v-model:selected="selected" :rows="rows" :form="form" :counts="tree.counts" />
        </section>
        <div class="document-tree__side">
          <RowPanel
            :row="selectedRow"
            :tree="tree"
            :form="form"
            @show="showAnchor"
            @changed="load()"
            @gone="rowGone"
            @dirty="(open) => (draftOpen = open)"
          />
          <SourcePane ref="source" :document-id="id" :page="page" :cited="cited" @go="showPage" />
        </div>
      </div>
    </template>
    <ConfirmDialog
      v-if="leaving"
      :title="t('documents.tree.leave.title')"
      :message="t('documents.tree.leave.message')"
      :confirm-label="t('documents.tree.leave.confirm')"
      :cancel-label="t('documents.tree.leave.cancel')"
      @confirm="answer(true)"
      @cancel="answer(false)"
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
