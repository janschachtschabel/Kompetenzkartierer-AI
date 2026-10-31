<script setup lang="ts">
/**
 * One document made of an entry's conversion (plan M1 7.5, 7a, 8b): what it is for, its extraction
 * (DocumentExtraction: followed, cancelled, started again), its work packages (DocumentUnits), what
 * the stages found on it with the repair offered to its owner (DocumentFindings) and the runs of its
 * stages (DocumentRuns). The page reads the document again when its extraction has moved on or a
 * repair was started, its work packages and findings at each progress too. No repair is offered
 * while a job of the document waits or runs: one followed under the extraction, or one just started
 * and not yet read with the document. Which revision it is stands at the top (RevisionNotice: frozen,
 * with the draft copy for an editor; or a draft copy); its work and edition beside its facts
 * (DocumentEdition); an editor freezes it below its findings (DocumentFreeze, plan M1 9.10, Paket 9d1),
 * the keyboard then taken to the notice that says so.
 */
import { computed, nextTick, onMounted, ref, watch } from "vue";
import { RouterLink } from "vue-router";

import { ApiError, getDocument, getRuns, type CurriculumDocument, type Run } from "@/api";
import DocumentEdition from "@/components/DocumentEdition.vue";
import DocumentExtraction from "@/components/DocumentExtraction.vue";
import DocumentFindings from "@/components/DocumentFindings.vue";
import DocumentFreeze from "@/components/DocumentFreeze.vue";
import DocumentRuns from "@/components/DocumentRuns.vue";
import DocumentUnits from "@/components/DocumentUnits.vue";
import EmptyState from "@/components/EmptyState.vue";
import ErrorState from "@/components/ErrorState.vue";
import LoadingState from "@/components/LoadingState.vue";
import RevisionNotice from "@/components/RevisionNotice.vue";
import { focusIsFree } from "@/focusRescue";
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
// A frozen document's notice led here to the draft copy it made (RevisionNotice.vue)
const copied = ref(false);
const notice = ref<InstanceType<typeof RevisionNotice> | null>(null);
// bumped as the extraction moves on: the work packages and the findings are read again
const unitsRead = ref(0);
// a job of the document waits or runs, as DocumentExtraction follows it
const jobOpen = ref(false);
// a repair was started, the document not read again since
const repairStarted = ref(false);

/** Whether the page that led here said `key`, said once: read again later, or come back to, the page no longer says so. */
function ledHere(key: "ledToRunning" | "copied"): boolean {
  const state: unknown = window.history.state;
  if (typeof state !== "object" || state === null || (state as Record<string, unknown>)[key] !== true) {
    return false;
  }
  window.history.replaceState({ ...state, [key]: undefined }, "");
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

// Frozen: the page shows it so at once, the keyboard - left on the button that went - taken to the notice
async function frozen(document: CurriculumDocument): Promise<void> {
  document_.value = document;
  await nextTick();
  if (focusIsFree()) notice.value?.focus();
  void load();
}

function moment(value: string): string {
  return momentFormat.format(new Date(value));
}

onMounted(() => {
  led.value = ledHere("ledToRunning");
  copied.value = ledHere("copied");
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
    led.value = ledHere("ledToRunning");
    copied.value = ledHere("copied");
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
      <RevisionNotice ref="notice" :key="document_.id" :document="document_" :copied="copied" @changed="load()" />
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
      <DocumentEdition :key="document_.id" class="document__section" :document="document_" @changed="load()" />
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
        :closed="document_.frozen_at !== null"
        @started="repairing()"
      />
      <DocumentFreeze
        :key="document_.id"
        class="document__section"
        :document="document_"
        @frozen="frozen"
        @changed="load()"
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
