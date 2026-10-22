<script setup lang="ts">
/**
 * One register entry with all the register knows of it: what it is, where it
 * comes from and on what terms it may be used - its licence and the evidence
 * where the register has them - and how its file came, each time it came; for a
 * seed's candidate what the dataset or the land's research said of the
 * curriculum, what the check found at its address, and the access notes of its
 * land, school form and subject.
 */
import { onMounted, ref, watch } from "vue";
import { RouterLink, useRouter, type RouteLocationRaw } from "vue-router";

import { ApiError, getSource, MIB, type SeedFields, type SourceDetail } from "@/api";
import AcquisitionList from "@/components/AcquisitionList.vue";
import EmptyState from "@/components/EmptyState.vue";
import ErrorState from "@/components/ErrorState.vue";
import LoadingState from "@/components/LoadingState.vue";
import { LOCALE, messages, momentFormat, t } from "@/i18n/de";
import { failureNotice, type Notice } from "@/notice";
import { pageTitle } from "@/pageTitle";
import { isWebAddress } from "@/readableAddress";
import { word } from "@/registerWords";

const props = defineProps<{ id: string }>();

const router = useRouter();
/** The register as the reader left it - filtered - where they came from it; else the register itself. */
const registerBack = ((): RouteLocationRaw => {
  const back = router.options.history.state.back;
  const left = typeof back === "string" ? router.resolve(back) : null;
  return left?.name === "sources" ? left.fullPath : { name: "sources" };
})();

const source = ref<SourceDetail | null>(null);
const loading = ref(true);
const missing = ref(false);
const failure = ref<Notice | null>(null);
// The latest question counts: an answer for an entry left meanwhile is dropped
let generation = 0;

async function load(): Promise<void> {
  const mine = ++generation;
  loading.value = true;
  failure.value = null;
  missing.value = false;
  try {
    const found = await getSource(props.id);
    if (mine === generation) source.value = found;
  } catch (error) {
    if (mine !== generation) return;
    source.value = null;
    // another account's upload is the 404 of an entry that does not exist; an id that is no
    // UUID (422) is no entry's at all - trying again could not help either
    if (error instanceof ApiError && (error.status === 404 || error.status === 422)) missing.value = true;
    else failure.value = failureNotice(error, t("entryPage.loadFailed"));
  } finally {
    if (mine === generation) loading.value = false;
  }
}

onMounted(load);
// The tab names the entry once it is known; until then the router's name for the page stands.
// A watcher stops with the page: an answer that comes after the reader left renames nothing.
watch(source, (found) => {
  if (found) document.title = pageTitle(found.title || found.url || t("app.titles.source"));
});
// another entry: the one before is not shown under its address while it loads
watch(
  () => props.id,
  () => {
    source.value = null;
    void load();
  },
);

const megabytes = new Intl.NumberFormat(LOCALE, { style: "unit", unit: "megabyte", maximumFractionDigits: 1 });
const kilobytes = new Intl.NumberFormat(LOCALE, { style: "unit", unit: "kilobyte", maximumFractionDigits: 0 });

/** A file's size as the upload limit counts it: MB of 2^20 bytes, below one a kB of 1024. */
function size(bytes: number): string {
  return bytes >= MIB ? megabytes.format(bytes / MIB) : kilobytes.format(bytes / 1024);
}

function grades(seed: SeedFields): string | null {
  const { grade_from: from, grade_to: to } = seed;
  if (from === null && to === null) return null;
  // one grade, or one end only: the grade itself
  if (from === null || to === null || from === to) return String(from ?? to);
  return t("entryPage.seed.gradeRange", { from, to });
}
</script>

<template>
  <div class="page source">
    <p class="source__back">
      <RouterLink :to="registerBack">{{ t("entryPage.back") }}</RouterLink>
    </p>
    <h1 v-if="source"><bdi class="source__title">{{ source.title || source.url }}</bdi></h1>
    <h1 v-else>{{ t("entryPage.heading") }}</h1>

    <LoadingState v-if="loading && !source" />
    <EmptyState v-else-if="missing" :level="2" :title="t('entryPage.notFoundTitle')" :body="t('entryPage.notFoundBody')" />
    <ErrorState
      v-else-if="failure"
      :message="failure.text"
      :reason="failure.reason"
      :explanation="failure.explanation"
      @retry="load()"
    />
    <template v-else-if="source">
      <section class="source__section" aria-labelledby="source-facts">
        <h2 id="source-facts">{{ t("entryPage.facts.heading") }}</h2>
        <dl class="facts">
          <dt>{{ t("entryPage.facts.provenance") }}</dt>
          <dd>{{ word(messages.sources.provenance, source.provenance) }}</dd>
          <dt>{{ t("entryPage.facts.status") }}</dt>
          <dd>{{ word(messages.sources.status, source.register_status) }}</dd>
          <dt>{{ t("entryPage.facts.rights") }}</dt>
          <dd>{{ word(messages.sources.rights, source.rights_status) }}</dd>
          <template v-if="source.license">
            <dt>{{ t("entryPage.facts.license") }}</dt>
            <dd><bdi>{{ source.license }}</bdi></dd>
          </template>
          <template v-if="source.rights_evidence">
            <dt>{{ t("entryPage.facts.rightsEvidence") }}</dt>
            <dd><bdi>{{ source.rights_evidence }}</bdi></dd>
          </template>
          <template v-if="source.source_type">
            <dt>{{ t("entryPage.facts.sourceType") }}</dt>
            <dd>{{ word(messages.entryPage.sourceType, source.source_type) }}</dd>
          </template>
          <template v-if="source.country">
            <dt>{{ t("entryPage.facts.country") }}</dt>
            <dd>{{ word(messages.sources.countries, source.country) }}</dd>
          </template>
          <template v-if="source.url">
            <dt>{{ t("entryPage.facts.address") }}</dt>
            <dd>
              <!-- noreferrer: the app's own address goes to no foreign server -->
              <a v-if="isWebAddress(source.url)" class="facts__address" :href="source.url" rel="noreferrer">
                <bdi>{{ source.url }}</bdi>
              </a>
              <bdi v-else class="facts__address">{{ source.url }}</bdi>
            </dd>
          </template>
          <dt>{{ t("entryPage.facts.file") }}</dt>
          <dd>
            <bdi v-if="source.file">{{ source.file.name }}</bdi>
            <template v-else>{{ t("sources.register.noFile") }}</template>
          </dd>
        </dl>
      </section>

      <section v-if="source.acquisitions.length" class="source__section" aria-labelledby="source-acquisitions">
        <h2 id="source-acquisitions">{{ t("entryPage.acquisitions.heading") }}</h2>
        <AcquisitionList :acquisitions="source.acquisitions" />
      </section>

      <section v-if="source.seed" class="source__section" aria-labelledby="source-seed">
        <h2 id="source-seed">{{ t("entryPage.seed.heading") }}</h2>
        <dl class="facts">
          <dt>{{ t("entryPage.seed.dataset") }}</dt>
          <dd>{{ word(messages.sources.provenance, source.seed.dataset) }}</dd>
          <template v-if="source.seed.school_form">
            <dt>{{ t("entryPage.seed.schoolForm") }}</dt>
            <dd>{{ source.seed.school_form }}</dd>
          </template>
          <template v-if="source.seed.stage">
            <dt>{{ t("entryPage.seed.stage") }}</dt>
            <dd>{{ source.seed.stage }}</dd>
          </template>
          <template v-if="source.seed.subject">
            <dt>{{ t("entryPage.seed.subject") }}</dt>
            <dd>{{ source.seed.subject }}</dd>
          </template>
          <template v-if="grades(source.seed)">
            <dt>{{ t("entryPage.seed.grades") }}</dt>
            <dd>{{ grades(source.seed) }}</dd>
          </template>
          <template v-if="source.seed.binding">
            <dt>{{ t("entryPage.seed.binding") }}</dt>
            <dd>{{ source.seed.binding }}</dd>
          </template>
          <template v-if="isWebAddress(source.seed.archive_url)">
            <dt>{{ t("entryPage.seed.archive") }}</dt>
            <dd>
              <a :href="source.seed.archive_url" rel="noreferrer">{{ t("entryPage.seed.archiveOpen") }}</a>
            </dd>
          </template>
          <template v-if="source.seed.evidence">
            <dt>{{ t("entryPage.seed.evidence") }}</dt>
            <dd>{{ word(messages.entryPage.evidence, source.seed.evidence) }}</dd>
          </template>
        </dl>
      </section>

      <section v-if="source.seed || source.check" class="source__section" aria-labelledby="source-check">
        <h2 id="source-check">{{ t("entryPage.check.heading") }}</h2>
        <dl v-if="source.check" class="facts">
          <dt>{{ t("entryPage.check.outcome") }}</dt>
          <dd>{{ word(messages.entryPage.outcome, source.check.outcome) }}</dd>
          <template v-if="source.check.status_code !== null">
            <dt>{{ t("entryPage.check.statusCode") }}</dt>
            <dd>{{ source.check.status_code }}</dd>
          </template>
          <template v-if="source.check.detected_type">
            <dt>{{ t("entryPage.check.kind") }}</dt>
            <dd>{{ word(messages.entryPage.kind, source.check.detected_type) }}</dd>
          </template>
          <template v-if="source.check.size !== null">
            <dt>{{ t("entryPage.check.size") }}</dt>
            <dd>{{ size(source.check.size) }}</dd>
          </template>
          <dt>{{ t("entryPage.check.checkedAt") }}</dt>
          <dd>
            <time :datetime="source.check.checked_at">{{ momentFormat.format(new Date(source.check.checked_at)) }}</time>
          </dd>
        </dl>
        <p v-else class="source__none">{{ t("entryPage.check.none") }}</p>
      </section>

      <section v-if="source.seed" class="source__section" aria-labelledby="source-notes">
        <h2 id="source-notes">{{ t("entryPage.notes.heading") }}</h2>
        <p class="source__lead">{{ t("entryPage.notes.intro") }}</p>
        <ul v-if="source.access_notes.length" class="notes">
          <li v-for="(note, index) in source.access_notes" :key="index" class="note card">
            <!-- a note that is its address alone (an archived copy) is said once, as the link -->
            <p v-if="note.text !== note.url" class="note__text">{{ note.text }}</p>
            <ul v-if="note.categories.length" class="note__categories">
              <li v-for="category in note.categories" :key="category" class="status-badge neutral">{{ category }}</li>
            </ul>
            <p v-if="isWebAddress(note.url)" class="note__address">
              <a :href="note.url" rel="noreferrer"><bdi>{{ note.url }}</bdi></a>
            </p>
          </li>
        </ul>
        <p v-else class="source__none">{{ t("entryPage.notes.none") }}</p>
      </section>
    </template>
  </div>
</template>

<style scoped>
.source__back {
  margin: 0 0 var(--space-2);
}

/* A long title or address breaks rather than pushing the page sideways at 320px; among the facts
   (style.css) an address does so too. */
.source__title,
.note__address {
  overflow-wrap: anywhere;
}

.source__section {
  margin-block-end: var(--space-4);
}

.source__lead,
.source__none {
  max-width: var(--reading-width);
  color: var(--text-muted);
  margin: 0 0 var(--space-2);
}

.notes {
  display: grid;
  gap: var(--space-1);
  margin: 0;
  padding: 0;
  list-style: none;
}

.note {
  margin: 0;
}

.note__text {
  margin: 0 0 var(--space-1);
}

.note__categories {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-0);
  margin: 0 0 var(--space-1);
  padding: 0;
  list-style: none;
}

.note__address {
  margin: 0;
  font-size: var(--step--1);
}
</style>
