<script setup lang="ts">
/**
 * One document made of an entry's conversion (plan M1 7.5, 7a): what it is for, its extraction and
 * the runs of its stages. An extraction waiting or running is followed here and can be cancelled
 * (JobProgress); one that ended - done, failed, cancelled - is started again by the document's
 * owner, and goes on where it stopped. Another account that sees the document (the editors) reads
 * it and is told who starts its extraction.
 */
import { computed, onMounted, ref, watch } from "vue";
import { RouterLink } from "vue-router";

import { ApiError, getDocument, getRuns, startExtraction, type CurriculumDocument, type Run } from "@/api";
import AppIcon from "@/components/AppIcon.vue";
import EmptyState from "@/components/EmptyState.vue";
import ErrorState from "@/components/ErrorState.vue";
import JobProgress from "@/components/JobProgress.vue";
import LoadingState from "@/components/LoadingState.vue";
import NoticeText from "@/components/NoticeText.vue";
import { messages, momentFormat, t } from "@/i18n/de";
import { hasEnded } from "@/jobWatch";
import { failureNotice, type Notice } from "@/notice";
import { pageTitle } from "@/pageTitle";
import { word } from "@/registerWords";

const props = defineProps<{ id: string }>();

const document_ = ref<CurriculumDocument | null>(null);
const runs = ref<Run[]>([]);
const loading = ref(true);
const missing = ref(false);
const failure = ref<Notice | null>(null);
/** The extraction job this page follows: the one waiting or running, or the one it just started. */
const followed = ref<string | null>(null);
const starting = ref(false);
const startFailure = ref<Notice | null>(null);
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
    const latest = found.extraction;
    followed.value = latest && !hasEnded(latest.status) ? latest.job_id : null;
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

async function resume(): Promise<void> {
  if (starting.value) return; // the button stays focusable while busy, so it can be pressed again
  starting.value = true;
  startFailure.value = null;
  try {
    followed.value = (await startExtraction(props.id)).id;
  } catch (error) {
    startFailure.value = failureNotice(error, t("documents.page.resumeFailed"));
  } finally {
    starting.value = false;
  }
}

function stageName(stage: string): string {
  return word(messages.documents.stages, stage);
}

function moment(value: string | null): string {
  return value ? momentFormat.format(new Date(value)) : "–";
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

      <section class="document__section" aria-labelledby="document-extraction">
        <h2 id="document-extraction">{{ t("documents.page.extraction") }}</h2>
        <JobProgress
          v-if="followed"
          :key="followed"
          :job-id="followed"
          :label="t('documents.page.jobLabel')"
          @ended="load()"
        />
        <template v-else>
          <p class="document__note">
            {{
              document_.extraction
                ? t("documents.page.lastStatus", { status: t(`jobs.status.${document_.extraction.status}`) })
                : t("documents.page.none")
            }}
          </p>
          <div v-if="document_.own" class="document__start">
            <p v-if="startFailure" class="field__error" role="alert">
              <AppIcon name="warning" /> <NoticeText :notice="startFailure" />
            </p>
            <!-- aria-disabled, not disabled: a disabled button drops the focus it holds -->
            <button
              type="button"
              class="btn primary"
              data-test="extraction-resume"
              :aria-disabled="starting || undefined"
              @click="resume"
            >
              {{ t("documents.page.resume") }}
            </button>
          </div>
          <p v-else class="document__note">{{ t("documents.page.notOwn") }}</p>
        </template>
      </section>

      <section class="document__section" aria-labelledby="document-runs">
        <h2 id="document-runs">{{ t("documents.page.runs") }}</h2>
        <!-- wider than a phone: scrolled on its own, by the keyboard too -->
        <div v-if="runs.length" class="document__runs" tabindex="0" role="region" :aria-label="t('documents.page.runsTable')">
          <table>
            <thead>
              <tr>
                <th scope="col">{{ t("documents.page.columns.stage") }}</th>
                <th scope="col">{{ t("documents.page.columns.attempt") }}</th>
                <th scope="col">{{ t("documents.page.columns.state") }}</th>
                <th scope="col">{{ t("documents.page.columns.started") }}</th>
                <th scope="col">{{ t("documents.page.columns.finished") }}</th>
                <th scope="col">{{ t("documents.page.columns.failure") }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(run, index) in runs" :key="index">
                <td>{{ stageName(run.stage) }}</td>
                <td>{{ run.attempt ?? "–" }}</td>
                <td>{{ word(messages.documents.runStates, run.state) }}</td>
                <td><time :datetime="run.started_at">{{ moment(run.started_at) }}</time></td>
                <td>
                  <time v-if="run.finished_at" :datetime="run.finished_at">{{ moment(run.finished_at) }}</time>
                  <template v-else>–</template>
                </td>
                <td><code v-if="run.failure">{{ run.failure }}</code></td>
              </tr>
            </tbody>
          </table>
        </div>
        <p v-else class="document__note">{{ t("documents.page.noRuns") }}</p>
      </section>
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

.document__note {
  max-width: var(--reading-width);
  color: var(--text-muted);
  margin: 0 0 var(--space-2);
}

.document__start {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: var(--space-1);
}

.document__runs {
  overflow-x: auto;
}

.document__runs table {
  border-collapse: collapse;
  min-width: 36rem;
}

.document__runs th,
.document__runs td {
  padding: var(--space-0) var(--space-2) var(--space-0) 0;
  text-align: start;
  vertical-align: top;
}

.document__runs code {
  overflow-wrap: anywhere;
}
</style>
