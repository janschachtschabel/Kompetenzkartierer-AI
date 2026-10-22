<script setup lang="ts">
/**
 * The source register: adding a document - a file, or an address the server
 * fetches - following the fetches started here, and the entries the account
 * sees, a page at a time.
 */
import { onMounted, ref } from "vue";

import { getInfo, listSources, type ImportStarted, type SourcePage } from "@/api";
import EmptyState from "@/components/EmptyState.vue";
import ErrorState from "@/components/ErrorState.vue";
import ImportForm from "@/components/ImportForm.vue";
import JobProgress from "@/components/JobProgress.vue";
import LoadingState from "@/components/LoadingState.vue";
import PartialState from "@/components/PartialState.vue";
import SourceTable from "@/components/SourceTable.vue";
import UploadForm from "@/components/UploadForm.vue";
import { t } from "@/i18n/de";
import { failureNotice, type Notice } from "@/notice";

interface Followed {
  jobId: string;
  label: string;
}

const page = ref<SourcePage | null>(null);
const loading = ref(true);
const loadingMore = ref(false);
/** The register did not load at all. */
const failure = ref<Notice | null>(null);
/** A reload or a further page did not, and what to try again. */
const partial = ref<{ notice: Notice; retry: () => void } | null>(null);
const maxUploadMb = ref<number | undefined>(undefined);
/** The fetches started on this page, newest first; they stay with how they ended. */
const followed = ref<Followed[]>([]);
// Each first page read counts: a further page asked for before it belongs to an older list.
let generation = 0;

async function load(): Promise<void> {
  const mine = ++generation;
  loading.value = true;
  failure.value = null;
  try {
    const first = await listSources();
    if (mine !== generation) return;
    page.value = first;
    partial.value = null;
  } catch (error) {
    if (mine !== generation) return;
    if (page.value) partial.value = { notice: failureNotice(error, t("sources.register.reloadFailed")), retry: () => void load() };
    else failure.value = failureNotice(error, t("sources.register.loadFailed"));
  } finally {
    if (mine === generation) loading.value = false;
  }
}

async function more(): Promise<void> {
  const current = page.value;
  if (!current || loadingMore.value) return; // the button stays focusable while busy
  const mine = generation;
  loadingMore.value = true;
  partial.value = null;
  try {
    const next = await listSources({}, { offset: current.entries.length });
    if (mine !== generation) return;
    // newest first: an entry added meanwhile pushed one of this page onto the next
    const shown = new Set(current.entries.map((entry) => entry.id));
    const added = next.entries.filter((entry) => !shown.has(entry.id));
    page.value = { ...next, offset: 0, entries: [...current.entries, ...added] };
  } catch (error) {
    if (mine === generation) partial.value = { notice: failureNotice(error, t("sources.register.moreFailed")), retry: () => void more() };
  } finally {
    loadingMore.value = false;
  }
}

function follow(started: ImportStarted, address: string): void {
  const label = started.source.title || address; // its title waits for the file
  followed.value = [{ jobId: started.job_id, label }, ...followed.value];
  void load(); // the new entry, before its file arrives
}

onMounted(async () => {
  void load();
  try {
    maxUploadMb.value = (await getInfo()).max_upload_mb;
  } catch {
    // Costs the file field its limit, not the upload: the server still refuses a file too large.
  }
});
</script>

<template>
  <div class="page sources">
    <h1>{{ t("sources.heading") }}</h1>
    <p class="sources__lead">{{ t("sources.intro") }}</p>

    <section class="sources__section" aria-labelledby="sources-add">
      <h2 id="sources-add">{{ t("sources.addHeading") }}</h2>
      <div class="sources__forms">
        <div class="card"><UploadForm :max-upload-mb="maxUploadMb" @uploaded="load" /></div>
        <div class="card"><ImportForm @imported="follow" /></div>
      </div>
    </section>

    <section v-if="followed.length" class="sources__section" aria-labelledby="sources-jobs">
      <h2 id="sources-jobs">{{ t("sources.jobs.heading") }}</h2>
      <ul class="sources__jobs">
        <li v-for="item in followed" :key="item.jobId" class="card">
          <JobProgress :job-id="item.jobId" :label="item.label" @ended="load" @gone="load" />
        </li>
      </ul>
    </section>

    <section class="sources__section" aria-labelledby="sources-register">
      <h2 id="sources-register">{{ t("sources.register.heading") }}</h2>
      <LoadingState v-if="loading && !page" />
      <ErrorState
        v-else-if="failure"
        :message="failure.text"
        :reason="failure.reason"
        :explanation="failure.explanation"
        @retry="load"
      />
      <EmptyState
        v-else-if="page && page.entries.length === 0"
        :level="3"
        :title="t('sources.register.emptyTitle')"
        :body="t('sources.register.emptyBody')"
      />
      <SourceTable
        v-else-if="page"
        :entries="page.entries"
        :total="page.total"
        :loading-more="loadingMore"
        @more="more"
      />
      <PartialState v-if="partial" class="sources__partial" :notice="partial.notice" retry @retry="partial.retry" />
    </section>
  </div>
</template>

<style scoped>
.sources__lead {
  max-width: var(--reading-width);
  font-size: var(--step-1);
  color: var(--text-muted);
  margin: 0 0 var(--space-3);
}

.sources__section {
  margin-block-end: var(--space-4);
}

/* Side by side where there is room, stacked on a phone, with no breakpoint to keep. */
.sources__forms {
  display: grid;
  gap: var(--space-2);
  grid-template-columns: repeat(auto-fit, minmax(min(20rem, 100%), 1fr));
  align-items: start;
}

.sources__forms .card,
.sources__jobs .card {
  margin: 0;
}

.sources__jobs {
  display: grid;
  gap: var(--space-1);
  margin: 0;
  padding: 0;
  list-style: none;
}

.sources__partial {
  margin-block-start: var(--space-2);
}
</style>
