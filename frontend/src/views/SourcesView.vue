<script setup lang="ts">
/**
 * The source register: adding a document - a file, or an address the server
 * fetches - following the fetches started here, and the entries the account
 * sees, a page at a time.
 */
import { onMounted, ref, watch } from "vue";

import { getInfo, listSources, MAX_PAGE_SIZE, PAGE_SIZE, type ImportStarted, type SourcePage } from "@/api";
import EmptyState from "@/components/EmptyState.vue";
import ErrorState from "@/components/ErrorState.vue";
import ImportForm from "@/components/ImportForm.vue";
import JobProgress from "@/components/JobProgress.vue";
import LoadingState from "@/components/LoadingState.vue";
import PartialState from "@/components/PartialState.vue";
import SourceTable from "@/components/SourceTable.vue";
import UploadForm from "@/components/UploadForm.vue";
import { focusIsFree } from "@/focusRescue";
import { t } from "@/i18n/de";
import { sayAnew } from "@/liveRegion";
import { failureNotice, type Notice } from "@/notice";

interface Followed {
  jobId: string;
  label: string;
}

/** Where the focus goes once the page shows what an action waited for, and where that action began. */
interface FocusRequest {
  target: () => HTMLElement | null | undefined;
  from: Element | null;
}

const page = ref<SourcePage | null>(null);
const loading = ref(true);
const loadingMore = ref(false);
/** The register did not load at all. */
const failure = ref<Notice | null>(null);
/** A reload or a further page did not, and what to try again; it stays until a try succeeds. */
const partial = ref<{ notice: Notice; retry: () => void } | null>(null);
const maxUploadMb = ref<number | undefined>(undefined);
/** The fetches started on this page, newest first; they stay with how they ended. */
const followed = ref<Followed[]>([]);
const table = ref<InstanceType<typeof SourceTable> | null>(null);
// Each first page read counts: a further page asked for before it belongs to an older list.
let generation = 0;
let focusRequest: FocusRequest | null = null;

// After the render, in the same flush - before the focus rescue moves a focus the render took to
// the main region. Only where the focus still rests where the action began, or nowhere: whoever
// went on to type elsewhere meanwhile keeps their place.
watch(
  page,
  () => {
    const request = focusRequest;
    focusRequest = null;
    if (request && (document.activeElement === request.from || focusIsFree())) request.target()?.focus();
  },
  { flush: "post" },
);

function registerHeading(): HTMLElement | null {
  return document.getElementById("sources-register");
}

/** The row after the entry `id`, as the page shows it then: an entry added above moves it down. */
function rowAfter(id: string): HTMLElement | undefined {
  const index = page.value?.entries.findIndex((entry) => entry.id === id) ?? -1;
  return index < 0 ? undefined : table.value?.row(index + 1);
}

/** The notice of a reload or a further page that did not come; the same one again is read out again. */
function fallShort(notice: Notice, retry: () => void): void {
  partial.value = { notice: { ...notice, text: sayAnew(partial.value?.notice.text ?? "", notice.text) }, retry };
}

/**
 * The register read again from its start: as many entries as it shows, so a later page and the
 * focus in it stay, and `extra` more. `focus` is where the focus goes once it shows them - the
 * register's heading after the notice's retry button went with the notice. `from` is where the
 * action began - the press of "Weitere laden", when a further page turned into this reading.
 */
async function load({
  extra = 0,
  focus,
  from = document.activeElement,
}: { extra?: number; focus?: FocusRequest["target"]; from?: Element | null } = {}): Promise<void> {
  const mine = ++generation;
  const limit = Math.min(MAX_PAGE_SIZE, Math.max(PAGE_SIZE, (page.value?.entries.length ?? 0) + extra));
  loading.value = true;
  failure.value = null;
  try {
    const first = await listSources({}, { limit });
    if (mine !== generation) return;
    if (focus) focusRequest = { target: focus, from };
    page.value = first;
    partial.value = null;
  } catch (error) {
    if (mine !== generation) return;
    if (page.value) {
      fallShort(failureNotice(error, t("sources.register.reloadFailed")), () => void load({ focus: registerHeading }));
    } else {
      failure.value = failureNotice(error, t("sources.register.loadFailed"));
    }
  } finally {
    if (mine === generation) loading.value = false;
  }
}

async function more(): Promise<void> {
  const current = page.value;
  // the button stays focusable while busy; while the register is read again, a further page of it is no page
  if (!current || loadingMore.value || loading.value) return;
  const mine = generation;
  const from = document.activeElement;
  // the first entry not read before follows the last one shown, wherever that one is by then
  const lastShown = current.entries[current.entries.length - 1]?.id ?? "";
  const firstAddedRow = () => rowAfter(lastShown);
  loadingMore.value = true;
  try {
    const next = await listSources({}, { offset: current.entries.length });
    if (mine !== generation || page.value !== current) return;
    // newest first: an entry added meanwhile pushed one already shown onto this page, and itself
    // lies before the first - read the register from its start, a page more than it showed
    const shown = new Set(current.entries.map((entry) => entry.id));
    if (next.entries.some((entry) => shown.has(entry.id))) {
      return void (await load({ extra: PAGE_SIZE, focus: firstAddedRow, from }));
    }
    focusRequest = { target: firstAddedRow, from };
    page.value = { ...next, offset: 0, entries: [...current.entries, ...next.entries] };
    partial.value = null;
  } catch (error) {
    if (mine === generation) fallShort(failureNotice(error, t("sources.register.moreFailed")), () => void more());
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
        <div class="card"><UploadForm :max-upload-mb="maxUploadMb" @uploaded="load()" /></div>
        <div class="card"><ImportForm @imported="follow" /></div>
      </div>
    </section>

    <section v-if="followed.length" class="sources__section" aria-labelledby="sources-jobs">
      <h2 id="sources-jobs">{{ t("sources.jobs.heading") }}</h2>
      <ul class="sources__jobs">
        <li v-for="item in followed" :key="item.jobId" class="card">
          <JobProgress :job-id="item.jobId" :label="item.label" @ended="load()" @gone="load()" />
        </li>
      </ul>
    </section>

    <section class="sources__section" aria-labelledby="sources-register">
      <!-- tabindex -1: where the focus goes when the notice's retry button goes with the notice -->
      <h2 id="sources-register" tabindex="-1">{{ t("sources.register.heading") }}</h2>
      <LoadingState v-if="loading && !page" />
      <ErrorState
        v-else-if="failure"
        :message="failure.text"
        :reason="failure.reason"
        :explanation="failure.explanation"
        @retry="load()"
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

/* Room only once it says something; empty, it waits in the page without a gap. */
.sources__partial:not(:empty) {
  margin-block-start: var(--space-2);
}
</style>
