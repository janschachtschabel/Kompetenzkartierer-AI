<script setup lang="ts">
/**
 * The blocks of an entry's converted file, a page at a time (X0): what the conversion read, in
 * reading order, each block and table cell with the ID a quote cites. The page is in the address
 * (`?seite=3`), so a page can be bookmarked and shared - its number alone, nothing of the file.
 * Once a page the reader moved to shows, its heading takes the keyboard and the move is said.
 */
import { computed, nextTick, onMounted, ref, watch } from "vue";
import { RouterLink, useRoute, useRouter } from "vue-router";

import { ApiError, getBlocks, getConversion, getSource, type BlockPage, type Conversion, type SourceDetail } from "@/api";
import BlockList from "@/components/BlockList.vue";
import EmptyState from "@/components/EmptyState.vue";
import ErrorState from "@/components/ErrorState.vue";
import LoadingState from "@/components/LoadingState.vue";
import PagePicker from "@/components/PagePicker.vue";
import { focusIsFree } from "@/focusRescue";
import { t } from "@/i18n/de";
import { sayAnew } from "@/liveRegion";
import { failureNotice, type Notice } from "@/notice";
import { pageTitle } from "@/pageTitle";

const PAGE_PARAM = "seite";
/** The refusals that say there are no blocks yet, and why, in the refusal's own words. */
const NOT_CONVERTED: ReadonlySet<string> = new Set(["no_conversion", "no_file", "not_converted"]);

const props = defineProps<{ id: string }>();
const route = useRoute();
const router = useRouter();

/** The page the address names: a whole number from 1; anything else is the first. */
function pageOf(value: unknown): number {
  const page = typeof value === "string" && /^\d{1,6}$/.test(value) ? Number(value) : 1;
  return Math.max(page, 1);
}

const page = computed(() => pageOf(route.query[PAGE_PARAM]));

/** Why no page can show: no such entry, a file for the editors alone, no blocks yet. */
interface Blocked {
  title: string;
  body: string;
  /** Where the way on leads: the entry, where its conversion is started, or the register. */
  to: "entry" | "register";
}

const source = ref<SourceDetail | null>(null);
const conversion = ref<Conversion | null>(null);
const loading = ref(true);
const blocked = ref<Blocked | null>(null);
const failure = ref<Notice | null>(null);
const shown = ref<BlockPage | null>(null);
const pageLoading = ref(false);
const pageFailure = ref<Notice | null>(null);
const pastEnd = ref(false);
const status = ref("");
const pageHeading = ref<HTMLElement | null>(null);
// The latest question counts: an answer for an entry or a page left meanwhile is dropped
let generation = 0;
let pageGeneration = 0;

const pages = computed(() => conversion.value?.pages ?? 0);
const printed = computed(() => conversion.value?.printed_pages?.[page.value - 1] ?? null);

function blockedBy(error: unknown): Blocked | null {
  if (!(error instanceof ApiError)) return null;
  // another account's upload is the 404 of an entry that does not exist; an id that is no UUID
  // (422) is no entry's at all
  if (error.status === 422 || (error.status === 404 && (!error.code || error.code === "not_found"))) {
    return { title: t("entryPage.notFoundTitle"), body: t("entryPage.notFoundBody"), to: "register" };
  }
  if (error.code === "file_hidden") {
    return { title: t("conversionPage.hiddenTitle"), body: t("refusals.file_hidden"), to: "entry" };
  }
  if (error.code && NOT_CONVERTED.has(error.code)) {
    return { title: t("conversionPage.notConvertedTitle"), body: t(`refusals.${error.code}`), to: "entry" };
  }
  return null;
}

/** The blocks of a conversion still under way, or failed, are none yet: its entry says how it is. */
function notDone(state: Conversion): Blocked {
  const body = state.status === "failed" ? t("conversionPage.failedBody") : t("refusals.not_converted");
  return { title: t("conversionPage.notConvertedTitle"), body, to: "entry" };
}

async function load(): Promise<void> {
  const mine = ++generation;
  pageGeneration += 1; // a page asked for under the entry before is no page of this one
  loading.value = true;
  blocked.value = null;
  failure.value = null;
  const [entry, state] = await Promise.allSettled([getSource(props.id), getConversion(props.id)]);
  if (mine !== generation) return;
  source.value = entry.status === "fulfilled" ? entry.value : null;
  conversion.value = state.status === "fulfilled" ? state.value : null;
  // the entry's refusal first: no entry is why there is no conversion either
  const refused = entry.status === "rejected" ? entry : state.status === "rejected" ? state : null;
  if (refused) {
    const error: unknown = refused.reason;
    blocked.value = blockedBy(error);
    if (!blocked.value) failure.value = failureNotice(error, t("conversionPage.loadFailed"));
  } else if (conversion.value && conversion.value.status !== "done") {
    blocked.value = notDone(conversion.value);
  }
  loading.value = false;
  if (!blocked.value && !failure.value) await showPage(page.value);
}

/**
 * The blocks of page `number`. `moved`: the reader asked for it - the move is said once the page
 * shows, and its heading takes the keyboard where the keyboard still rests where the move began,
 * or nowhere; whoever went on elsewhere meanwhile keeps their place.
 */
async function showPage(number: number, { moved = false } = {}): Promise<void> {
  const mine = ++pageGeneration;
  const from = document.activeElement;
  shown.value = null;
  pageFailure.value = null;
  pastEnd.value = number > pages.value;
  if (!pastEnd.value) {
    pageLoading.value = true;
    try {
      const found = await getBlocks(props.id, number);
      if (mine !== pageGeneration) return;
      shown.value = found;
    } catch (error) {
      if (mine !== pageGeneration) return;
      if (error instanceof ApiError && error.code === "no_such_page") pastEnd.value = true;
      else blocked.value = blockedBy(error);
      if (!pastEnd.value && !blocked.value) pageFailure.value = failureNotice(error, t("conversionPage.pageFailed"));
    } finally {
      if (mine === pageGeneration) pageLoading.value = false;
    }
  }
  if (!moved || blocked.value) return;
  // a failure says itself, as an alert
  if (shown.value) status.value = sayAnew(status.value, arrival(shown.value));
  else if (pastEnd.value) status.value = sayAnew(status.value, t("conversionPage.noPageTitle"));
  await nextTick();
  if (document.activeElement === from || focusIsFree()) pageHeading.value?.focus();
}

function arrival(found: BlockPage): string {
  return t("conversionPage.announce", { page: found.page, pages: pages.value, count: found.blocks.length });
}

/** Replace, not push: a page turned is no step the way back has to walk - it leads to the entry. */
function go(number: number): void {
  void router.replace({ query: number === 1 ? {} : { [PAGE_PARAM]: String(number) } });
}

onMounted(load);
watch(page, (number) => {
  if (!loading.value && !blocked.value && !failure.value) void showPage(number, { moved: true });
});
// another entry: the one before is not shown under its address while it loads
watch(
  () => props.id,
  () => {
    source.value = null;
    conversion.value = null;
    shown.value = null;
    void load();
  },
);
// The tab names the entry and the page; the router names the page alone on each move, before this.
watch([source, page], ([entry, number]) => {
  const title = entry ? entry.title || entry.url || t("app.titles.source") : null;
  if (title) document.title = pageTitle(t("conversionPage.tabTitle", { title, page: number }));
});
</script>

<template>
  <div class="page conversion-page">
    <p class="conversion-page__back">
      <RouterLink :to="{ name: 'source', params: { id } }">{{ t("conversionPage.back") }}</RouterLink>
    </p>
    <h1 v-if="source"><bdi class="conversion-page__title">{{ source.title || source.url }}</bdi></h1>
    <h1 v-else>{{ t("conversionPage.heading") }}</h1>
    <p class="conversion-page__lead">{{ t("conversionPage.intro") }}</p>

    <LoadingState v-if="loading" />
    <EmptyState v-else-if="blocked" :level="2" :title="blocked.title" :body="blocked.body">
      <RouterLink v-if="blocked.to === 'entry'" data-test="to-entry" :to="{ name: 'source', params: { id } }">
        {{ t("conversionPage.toEntry") }}
      </RouterLink>
      <RouterLink v-else data-test="to-register" :to="{ name: 'sources' }">{{ t("entryPage.back") }}</RouterLink>
    </EmptyState>
    <ErrorState
      v-else-if="failure"
      :message="failure.text"
      :reason="failure.reason"
      :explanation="failure.explanation"
      @retry="load()"
    />
    <section v-else aria-labelledby="conversion-page-heading">
      <PagePicker :page="page" :pages="pages" @go="go" />
      <!-- tabindex -1: where the keyboard goes once a page the reader moved to shows -->
      <h2 id="conversion-page-heading" ref="pageHeading" tabindex="-1">
        {{ t("conversionPage.pageHeading", { page, pages }) }}
      </h2>
      <p v-if="printed" class="conversion-page__printed" data-test="printed">{{ t("conversionPage.printed", { printed }) }}</p>
      <LoadingState v-if="pageLoading" />
      <EmptyState v-else-if="pastEnd" :level="3" :title="t('conversionPage.noPageTitle')" :body="t('conversionPage.noPageBody', { pages })">
        <RouterLink data-test="first-page" :to="{ query: {} }" replace>{{ t("conversionPage.firstPage") }}</RouterLink>
      </EmptyState>
      <ErrorState
        v-else-if="pageFailure"
        :message="pageFailure.text"
        :reason="pageFailure.reason"
        :explanation="pageFailure.explanation"
        @retry="showPage(page, { moved: true })"
      />
      <EmptyState
        v-else-if="shown && shown.blocks.length === 0"
        :level="3"
        :title="t('conversionPage.emptyTitle')"
        :body="t('conversionPage.emptyBody')"
      />
      <BlockList v-else-if="shown" :blocks="shown.blocks" />
    </section>
    <!-- always in the page, so the first move is read out -->
    <p class="visually-hidden" role="status" data-test="page-status">{{ status }}</p>
  </div>
</template>

<style scoped>
.conversion-page__back {
  margin: 0 0 var(--space-2);
}

/* A long title breaks rather than pushing the page sideways at 320px. */
.conversion-page__title {
  overflow-wrap: anywhere;
}

.conversion-page__lead {
  max-width: var(--reading-width);
  color: var(--text-muted);
  margin: 0 0 var(--space-3);
}

.conversion-page__printed {
  margin: 0 0 var(--space-2);
  color: var(--text-muted);
  font-size: var(--step--1);
}
</style>
