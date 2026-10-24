<script setup lang="ts">
/**
 * One document made of an entry's conversion (plan M1 7.5, 7a): what it is for, its extraction
 * (DocumentExtraction: followed, cancelled, started again) and the runs of its stages
 * (DocumentRuns). The page reads the document again when its extraction has moved on.
 */
import { computed, onMounted, ref, watch } from "vue";
import { RouterLink } from "vue-router";

import { ApiError, getDocument, getRuns, type CurriculumDocument, type Run } from "@/api";
import DocumentExtraction from "@/components/DocumentExtraction.vue";
import DocumentRuns from "@/components/DocumentRuns.vue";
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

function moment(value: string): string {
  return momentFormat.format(new Date(value));
}

onMounted(load);
// The tab names the document once it is known; until then the router's name for the page stands
watch(heading, (name) => {
  if (name) document.title = pageTitle(name);
});
watch(
  () => props.id,
  () => {
    document_.value = null;
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
          <dt>{{ t("documents.page.facts.created") }}</dt>
          <dd><time :datetime="document_.created_at">{{ moment(document_.created_at) }}</time></dd>
        </dl>
      </section>
      <!-- keyed: what a start of the document before gave back late stays with that one -->
      <DocumentExtraction :key="document_.id" class="document__section" :document="document_" @changed="load()" />
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
