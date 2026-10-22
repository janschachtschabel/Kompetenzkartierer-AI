<script setup lang="ts">
/**
 * The source register: adding a document - a file, or an address the server
 * fetches - following the fetches started here, and the entries the account
 * sees, a page at a time, as far as the filter lets them through.
 */
import { onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

import { getInfo, type ImportStarted } from "@/api";
import CheckStart from "@/components/CheckStart.vue";
import EmptyState from "@/components/EmptyState.vue";
import ErrorState from "@/components/ErrorState.vue";
import ImportForm from "@/components/ImportForm.vue";
import JobProgress from "@/components/JobProgress.vue";
import LoadingState from "@/components/LoadingState.vue";
import PartialState from "@/components/PartialState.vue";
import RegisterFilter from "@/components/RegisterFilter.vue";
import SourceTable from "@/components/SourceTable.vue";
import UploadForm from "@/components/UploadForm.vue";
import { t } from "@/i18n/de";
import { emptyAdvice, filtersFromQuery, queryOf, sameFilters, type RegisterFilters } from "@/registerFilters";
import { hasRole } from "@/session";
import { useRegisterPage } from "@/useRegisterPage";

interface Followed {
  jobId: string;
  label: string;
}

const maxUploadMb = ref<number | undefined>(undefined);
/** The fetches and checks started on this page, newest first; they stay with how they ended. */
const followed = ref<Followed[]>([]);
const table = ref<InstanceType<typeof SourceTable> | null>(null);
const route = useRoute();
const router = useRouter();
// The filter as the address holds it: the way back from an entry's page finds it again
const filters = ref<RegisterFilters>(filtersFromQuery(route.query));

function registerHeading(): HTMLElement | null {
  return document.getElementById("sources-register");
}

const { page, loading, loadingMore, failure, partial, readWith, pageFiltered, filterNotice, load, more } =
  useRegisterPage(filters, { heading: registerHeading, row: (index) => table.value?.row(index) });

// replace, not push: a filter's change is no step the way back has to walk
watch(filters, (value) => {
  void router.replace({ query: queryOf(value) });
  void load();
});

// The address changed from elsewhere - the navigation's link to the register, without the
// filter: the filter follows it. Its own changes come back the same. Only under the route the
// page was mounted at: a KeepAlive or a leaving Transition keeps it mounted under the next page's
// address, which it would read with and write its query into. The route's name, not its path:
// the router takes "/Quellen/" for "/quellen", and the link then leads to the same page.
const ownRoute = route.name;
watch(
  () => route.query,
  (query) => {
    if (route.name !== ownRoute) return;
    const held = filtersFromQuery(query);
    if (!sameFilters(held, filters.value)) filters.value = held;
  },
);

function follow(started: ImportStarted, address: string): void {
  const label = started.source.title || address; // its title waits for the file
  followed.value = [{ jobId: started.job_id, label }, ...followed.value];
  void load(); // the new entry, before its file arrives
}

/** The check of the seed, once: a press that found it running already hands on the same job. */
function followCheck(jobId: string): void {
  if (followed.value.some((item) => item.jobId === jobId)) return;
  followed.value = [{ jobId, label: t("sources.check.jobLabel") }, ...followed.value];
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
        <div class="card"><UploadForm :max-upload-mb="maxUploadMb" @uploaded="load()" /></div>
        <div class="card"><ImportForm @imported="follow" /></div>
      </div>
    </section>

    <div v-if="hasRole('admin')" class="sources__section">
      <CheckStart @started="followCheck" />
    </div>

    <section v-if="followed.length" class="sources__section" aria-labelledby="sources-jobs">
      <h2 id="sources-jobs">{{ t("sources.jobs.heading") }}</h2>
      <ul class="sources__jobs">
        <li v-for="item in followed" :key="item.jobId" class="card">
          <JobProgress :job-id="item.jobId" :label="item.label" @ended="load()" @gone="load()" />
        </li>
      </ul>
    </section>

    <section class="sources__section" aria-labelledby="sources-register">
      <div class="sources__register-head">
        <!-- tabindex -1: where the focus goes when the notice's retry button goes with the notice -->
        <h2 id="sources-register" tabindex="-1">{{ t("sources.register.heading") }}</h2>
        <!-- the fade alone is barely seen. Quiet: the filter's status says what the reading brings,
             and a live region here would say each change of the filter. Not at the first reading,
             which the loading state shows in the table's place -->
        <LoadingState
          class="sources__reading"
          :class="{ 'sources__reading--idle': !(loading && page) }"
          data-test="reading"
          quiet
          :label="t('sources.register.reading')"
        />
      </div>
      <RegisterFilter v-model="filters" />
      <!-- always in the page, so the first "nothing matches" is read out -->
      <p class="visually-hidden" role="status" data-test="filter-status">{{ filterNotice }}</p>
      <LoadingState v-if="loading && !page" />
      <!-- busy while what it shows is read again; the controls and the regions that speak stay
           outside, as a busy region's changes wait to be read -->
      <div v-else class="sources__results" :aria-busy="loading || undefined">
        <ErrorState
          v-if="failure"
          :message="failure.text"
          :reason="failure.reason"
          :explanation="failure.explanation"
          @retry="load({ focus: registerHeading })"
        />
        <EmptyState
          v-else-if="page && page.entries.length === 0 && pageFiltered"
          :level="3"
          :title="t('sources.filter.emptyTitle')"
          :body="emptyAdvice(readWith)"
        />
        <EmptyState
          v-else-if="page && page.entries.length === 0"
          :level="3"
          :title="t('sources.register.emptyTitle')"
          :body="t('sources.register.emptyBody')"
        />
        <SourceTable
          v-else-if="page"
          ref="table"
          :entries="page.entries"
          :total="page.total"
          :loading-more="loadingMore || loading"
          @more="more"
        />
      </div>
      <!-- always in the page, so its first notice is read out -->
      <PartialState
        class="sources__partial"
        :notice="partial?.notice ?? null"
        :retry="partial !== null"
        @retry="partial?.retry()"
      />
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

/* The heading's space below it moves to the row, whose margin meets the filter's as the heading's
   did; the sign beside the heading wraps under it on a narrow screen. */
.sources__register-head {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 0 var(--space-2);
  margin: 0 0 var(--space-1);
}

.sources__register-head h2,
.sources__reading {
  margin: 0;
}

/* Shown only once a reading has lasted a moment, so a quick answer does not flash it; gone at
   once. A delay, no motion: the reduced-motion rule shortens durations, not this. */
.sources__reading {
  transition: visibility 0s linear 300ms;
}

/* Idle, the sign keeps its room: the table under it does not move when a reading starts. */
.sources__reading--idle {
  visibility: hidden;
  transition-delay: 0s;
}

/* Read again, what the register shows fades a little and the pointer says it is busy; the
   reading's end restores it. No motion where the system asked for none (style.css). */
.sources__results {
  transition: opacity var(--dur-2) var(--ease);
}

.sources__results[aria-busy="true"] {
  opacity: var(--busy-opacity);
  cursor: progress;
}

/* Room only once it says something; empty, it waits in the page without a gap. */
.sources__partial:not(:empty) {
  margin-block-start: var(--space-2);
}
</style>
