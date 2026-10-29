<script setup lang="ts">
/**
 * A document's tree page (plan M1 9.7-9.9, Paket 9c J2): its nodes and statements as a tree (TreeView), the
 * row chosen with its fields and anchors (RowDetail), and beside it the source - a page of the conversion the
 * document was read off, the blocks the row's anchors name marked (SourcePane). The row chosen and the page
 * of the source stand in the address (?zeile=node:<id>&seite=3), so back, forward and a reload keep them; a
 * row chosen goes to the page of its first anchor. Wide, the tree and the side stand side by side.
 */
import { computed, onMounted, toRef, watch } from "vue";
import { RouterLink, useRoute, useRouter } from "vue-router";

import { PAGE_PARAM } from "@/blockPages";
import EmptyState from "@/components/EmptyState.vue";
import ErrorState from "@/components/ErrorState.vue";
import LoadingState from "@/components/LoadingState.vue";
import RowDetail from "@/components/RowDetail.vue";
import SourcePane from "@/components/SourcePane.vue";
import TreeView from "@/components/TreeView.vue";
import { ROW_PARAM, useDocumentTree, type Row, type RowKey } from "@/documentTree";
import { t } from "@/i18n/de";
import { pageTitle } from "@/pageTitle";

const props = defineProps<{ id: string }>();
const route = useRoute();
const router = useRouter();
const { document: document_, tree, form, rows, loading, missing, failure, load } = useDocumentTree(toRef(props, "id"));

function anchorsOf(row: Row | null): { page_start: number | null; blocks: string[] }[] {
  if (!row) return [];
  return row.kind === "node" ? row.node.anchors : row.statement.anchors;
}

function firstPage(row: Row | null): number | null {
  return anchorsOf(row).find((anchor) => anchor.page_start !== null)?.page_start ?? null;
}

const selectedRow = computed<Row | null>(() => {
  const key = route.query[ROW_PARAM];
  return typeof key === "string" ? (rows.value.get(key as RowKey) ?? null) : null;
});

const selected = computed<RowKey | null>({
  get: () => selectedRow.value?.key ?? null,
  set: (key) => {
    const row = key ? (rows.value.get(key) ?? null) : null;
    const at = firstPage(row);
    void router.replace({
      query: { ...route.query, [ROW_PARAM]: key ?? undefined, ...(at ? { [PAGE_PARAM]: String(at) } : {}) },
    });
  },
});

const page = computed(() => {
  const asked = Number(route.query[PAGE_PARAM]);
  return Number.isInteger(asked) && asked >= 1 ? asked : (firstPage(selectedRow.value) ?? 1);
});

const cited = computed(() => [...new Set(anchorsOf(selectedRow.value).flatMap((anchor) => anchor.blocks))]);

const heading = computed(() =>
  document_.value
    ? t("documents.tree.heading", { title: document_.value.title || t("documents.untitled") })
    : t("app.titles.documentTree"),
);

const detailHeading = computed(() => {
  const row = selectedRow.value;
  if (!row) return t("documents.tree.detail.heading");
  if (row.kind === "statement") return t("documents.tree.detail.statement");
  const { code, original_title: title } = row.node.fields;
  const name = [code, title].filter((part) => typeof part === "string" && part).join(" ");
  return t("documents.tree.detail.node", { name: name || t("documents.tree.untitled") });
});

function showPage(at: number): void {
  void router.replace({ query: { ...route.query, [PAGE_PARAM]: String(at) } });
}

onMounted(() => void load());
watch(
  () => props.id,
  () => void load(),
);
// The tab names the document once it is known; until then the router's name for the page stands
watch(heading, (name) => {
  if (document_.value) document.title = pageTitle(name);
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
    <ErrorState
      v-else-if="failure && !tree"
      :message="failure.text"
      :reason="failure.reason"
      :explanation="failure.explanation"
      @retry="load()"
    />
    <div v-else-if="tree && form" class="document-tree__panes">
      <section class="document-tree__tree" aria-labelledby="document-tree-rows">
        <h2 id="document-tree-rows">{{ t("documents.tree.treeHeading") }}</h2>
        <TreeView v-model:selected="selected" :rows="rows" :form="form" :counts="tree.counts" />
      </section>
      <div class="document-tree__side">
        <section aria-labelledby="document-tree-detail">
          <h2 id="document-tree-detail">
            <bdi>{{ detailHeading }}</bdi>
          </h2>
          <RowDetail v-if="selectedRow" :row="selectedRow" :form="form" @show="showPage" />
          <p v-else>{{ t("documents.tree.detail.none") }}</p>
        </section>
        <SourcePane :document-id="id" :page="page" :cited="cited" @go="showPage" />
      </div>
    </div>
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
