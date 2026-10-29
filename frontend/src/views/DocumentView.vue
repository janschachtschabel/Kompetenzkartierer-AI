<script setup lang="ts">
/**
 * One document made of an entry's conversion (plan M1 7.5, 7a, 8b): what it is for, its extraction
 * (DocumentExtraction: followed, cancelled, started again), its work packages (DocumentUnits), what
 * the stages found on it with the repair offered to its owner (DocumentFindings) and the runs of its
 * stages (DocumentRuns). The page reads the document again when its extraction has moved on or a
 * repair was started, its work packages and findings at each progress too. No repair is offered
 * while a job of the document waits or runs: one followed under the extraction, or one just started
 * and not yet read with the document.
 */
import { computed, onMounted, ref, watch } from "vue";
import { RouterLink } from "vue-router";

import { ApiError, getDocument, getRuns, type CurriculumDocument, type Run } from "@/api";
import DocumentExtraction from "@/components/DocumentExtraction.vue";
import DocumentFindings from "@/components/DocumentFindings.vue";
import DocumentRuns from "@/components/DocumentRuns.vue";
import DocumentUnits from "@/components/DocumentUnits.vue";
import EmptyState from "@/components/EmptyState.vue";
import ErrorState from "@/components/ErrorState.vue";
import LoadingState from "@/components/LoadingState.vue";
import { messages, momentFormat, t } from "@/i18n/de";
import { failureNotice, type Notice } from "@/notice";
import { pageTitle } from "@/pageTitle";
import { word } from "@/registerWords";

const props = defineProps<{ id: string }>();

const document_ = ref<CurriculumDocument | null>(null);
const runs = ref<Run[]>([]);
const loading = ref(true);
const missing = ref(false);
const failure = ref<Notice | null>(null);
// The latest question counts: an answer for a document left meanwhile is dropped
let generation = 0;
// The start form led here to an extraction that ran already for the PDF (ExtractionStart.vue)
const led = ref(false);
// bumped as the extraction moves on: the work packages and the findings are read again
const unitsRead = ref(0);
// a job of the document waits or runs, as DocumentExtraction follows it
const jobOpen = ref(false);
// a repair was started, the document not read again since
const repairStarted = ref(false);

/** Whether a start led here, said once: read again later, or come back to, the page no longer says so. */
function ledHere(): boolean {
  const state: unknown = window.history.state;
  if (typeof state !== "object" || state === null || (state as Record<string, unknown>).ledToRunning !== true) {
    return false;
  }
  window.history.replaceState({ ...state, ledToRunning: undefined }, "");
  return true;
}

const heading = computed(() => (document_.value ? document_.value.title || t("documents.untitled") : ""));
const regions = computed(() =>
  (document_.value?.regions ?? []).map((code) => word(messages.sources.countries, code)).join(", "),
);

async function load(): Promise<void> {
  const mine = ++generation;
  loading.value = true;
  failure.value = null;
  missing.value = false;
  try {
    const [found, ran] = await Promise.all([getDocument(props.id), getRuns(props.id)]);
    if (mine !== generation) return;
    document_.value = found;
    runs.value = ran;
    repairStarted.value = false; // the document names its job now
  } catch (error) {
    if (mine !== generation) return;
    document_.value = null;
    // another's document is the 404 of one that does not exist; an id that is no UUID (422) none at all
    if (error instanceof ApiError && (error.status === 404 || error.status === 422)) missing.value = true;
    else failure.value = failureNotice(error, t("documents.page.loadFailed"));
  } finally {
    if (mine === generation) loading.value = false;
  }
}

function moved(): void {
  unitsRead.value++;
  void load();
}

function repairing(): void {
  repairStarted.value = true;
  moved();
}

function moment(value: string): string {
  return momentFormat.format(new Date(value));
}

onMounted(() => {
  led.value = ledHere();
  void load();
});
// The tab names the document once it is known; until then the router's name for the page stands
watch(heading, (name) => {
  if (name) document.title = pageTitle(name);
});
watch(
  () => props.id,
  () => {
    document_.value = null;
    led.value = ledHere();
    void load();
  },
);
</script>

<template>
  <div class="page document">
    <h1 v-if="document_"><bdi class="document__title">{{ heading }}</bdi></h1>
    <h1 v-else>{{ t("app.titles.document") }}</h1>

    <LoadingState v-if="loading && !document_" />
    <EmptyState
      v-else-if="missing"
      :level="2"
      :title="t('documents.page.notFoundTitle')"
      :body="t('documents.page.notFoundBody')"
    />
    <ErrorState
      v-else-if="failure"
      :message="failure.text"
      :reason="failure.reason"
      :explanation="failure.explanation"
      @retry="load()"
    />
    <template v-else-if="document_">
      <section class="document__section" aria-labelledby="document-facts">
        <h2 id="document-facts">{{ t("documents.page.facts.heading") }}</h2>
        <dl class="facts">
          <dt>{{ t("documents.page.facts.sector") }}</dt>
          <dd>{{ word(messages.documents.sectors, document_.sector) }}</dd>
          <dt>{{ t("documents.page.facts.regions") }}</dt>
          <dd>{{ regions || t("documents.page.noRegions") }}</dd>
          <dt>{{ t("documents.page.facts.source") }}</dt>
          <dd>
            <RouterLink data-test="document-source" :to="{ name: 'source', params: { id: document_.source_id } }">
              {{ t("documents.page.sourceLink") }}
            </RouterLink>
          </dd>
          <dt>{{ t("documents.page.facts.tree") }}</dt>
          <dd>
            <RouterLink data-test="document-tree" :to="{ name: 'documentTree', params: { id: document_.id } }">
              {{ t("documents.page.treeLink") }}
            </RouterLink>
          </dd>
          <dt>{{ t("documents.page.facts.created") }}</dt>
          <dd><time :datetime="document_.created_at">{{ moment(document_.created_at) }}</time></dd>
        </dl>
      </section>
      <!-- keyed: what a start of the document before gave back late stays with that one -->
      <DocumentExtraction
        :key="document_.id"
        class="document__section"
        :document="document_"
        :led="led"
        @changed="moved()"
        @progressed="unitsRead++"
        @busy="jobOpen = $event"
      />
      <DocumentUnits :key="document_.id" class="document__section" :document-id="document_.id" :refresh="unitsRead" />
      <DocumentFindings
        :key="document_.id"
        class="document__section"
        :document-id="document_.id"
        :own="document_.own"
        :busy="jobOpen || repairStarted"
        :refresh="unitsRead"
        @started="repairing()"
      />
      <DocumentRuns class="document__section" :runs="runs" />
    </template>
  </div>
</template>

<style scoped>
.document__title {
  overflow-wrap: anywhere;
}

.document__section {
  margin-block-start: var(--space-4);
}
</style>
