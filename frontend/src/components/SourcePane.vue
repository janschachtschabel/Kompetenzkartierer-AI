<script setup lang="ts">
/**
 * The source under a row (plan M1 9.9, Paket 9c J9): a page of the conversion the document was read off
 * (GET …/blocks), the blocks the row's anchors name marked (BlockList), and the pager to any other page.
 * Which page shows is the view's, which keeps it in the address; this only asks for one. As on the blocks'
 * page (ConversionView): a page asked for shows that it loads, the pager names it at once, and once it shows
 * the move is said. Its heading then takes the keyboard where the move began here - the pager, the way to
 * the first page, a retry, a table's first page - and the keyboard still rests there, or where it rests
 * nowhere; a move begun elsewhere (a row chosen in the tree) or a reader gone on meanwhile keeps their place,
 * and the view takes the keyboard along for an anchor's page (`focus`). The latest page asked for counts.
 * Why it shows none it says: a page past the end (with the way to the first), the content no longer the
 * reader's (which no retry changes, and no other page), a failed reading (with a retry). While a statement's
 * anchor is chosen (`picking`, Paket 9c2b L3) the blocks of the page shown are toggles; those chosen are taken
 * as one anchor, or the page as one its passage was not found on, told to the view (`anchor`) and said. The
 * choice is this page's for this statement: another page or another statement lets it go.
 */
import { computed, nextTick, ref, useId, watch } from "vue";

import { anchorCodeText, encodeAnchor } from "@/anchorDraft";
import { useAnchorPick } from "@/anchorPick";
import { ApiError, getDocumentBlocks, type DocumentPage } from "@/api";
import AnchorPickBar from "@/components/AnchorPickBar.vue";
import BlockList from "@/components/BlockList.vue";
import EmptyState from "@/components/EmptyState.vue";
import ErrorState from "@/components/ErrorState.vue";
import LoadingState from "@/components/LoadingState.vue";
import PagePicker from "@/components/PagePicker.vue";
import { focusIsFree } from "@/focusRescue";
import { t } from "@/i18n/de";
import { sayAnew } from "@/liveRegion";
import { failureNotice, type Notice } from "@/notice";

const props = withDefaults(
  defineProps<{
    documentId: string;
    page: number;
    cited: string[];
    /** The statement whose anchor is chosen here (its row's key); none while none is. */
    picking?: string | null;
  }>(),
  { picking: null },
);
const emit = defineEmits<{ go: [page: number]; anchor: [code: string] }>();

const headingId = useId();
const section = ref<HTMLElement | null>(null);
const heading = ref<HTMLElement | null>(null);
const shown = ref<DocumentPage | null>(null);
// the count of pages the last page read said: the pager stays while another page loads or fails
const pages = ref<number | null>(null);
const pending = ref(false);
const pastEnd = ref(false);
const hidden = ref(false);
const failure = ref<Notice | null>(null);
const status = ref("");
const citedBlocks = computed(() => new Set(props.cited));
const printed = computed(() => (shown.value?.page === props.page ? shown.value.printed_page : null));
const { picked, toggle, take } = useAnchorPick([() => props.documentId, () => props.page, () => props.picking]);
let generation = 0;

async function load({ moved = false } = {}): Promise<void> {
  const mine = ++generation;
  const from = document.activeElement;
  shown.value = null;
  pastEnd.value = false;
  // a refusal of the content stands until an answer says otherwise: no pager meanwhile
  failure.value = null;
  pending.value = true;
  try {
    const found = await getDocumentBlocks(props.documentId, props.page);
    if (mine !== generation) return;
    shown.value = found;
    pages.value = found.pages;
    hidden.value = false;
  } catch (error) {
    if (mine !== generation) return;
    hidden.value = error instanceof ApiError && error.code === "file_hidden";
    if (error instanceof ApiError && error.code === "no_such_page") pastEnd.value = true;
    else if (!hidden.value) failure.value = failureNotice(error, t("documents.tree.source.loadFailed"));
  } finally {
    if (mine === generation) pending.value = false;
  }
  if (!moved || mine !== generation) return;
  // a failure says itself, as an alert
  if (shown.value) {
    const count = shown.value.blocks.length + shown.value.continued.length;
    status.value = sayAnew(status.value, t("conversionPage.announce", { page: props.page, pages: shown.value.pages, count }));
  } else if (pastEnd.value) status.value = sayAnew(status.value, t("conversionPage.noPageTitle"));
  else if (hidden.value) status.value = sayAnew(status.value, t("conversionPage.hiddenTitle"));
  await nextTick();
  const stayed = document.activeElement === from && from !== null && section.value?.contains(from);
  if (stayed || focusIsFree()) focus();
}

/** The keyboard to the source's heading. */
function focus(): void {
  heading.value?.focus();
}

defineExpose({ focus });

watch(
  () => props.documentId,
  () => {
    pages.value = null;
    void load();
  },
  { immediate: true },
);
watch(
  () => props.page,
  () => void load({ moved: true }),
);
// an anchor chosen goes to the view, and is said
function give(code: string | null): void {
  if (!code) return;
  emit("anchor", code);
  status.value = sayAnew(status.value, t("documents.tree.source.taken", { anchor: anchorCodeText(code) }));
}
</script>

<template>
  <section ref="section" class="source" :aria-labelledby="headingId">
    <!-- tabindex -1: where the keyboard goes once a page the reader moved to shows -->
    <h2 :id="headingId" ref="heading" tabindex="-1">{{ t("documents.tree.source.heading") }}</h2>
    <!-- not where the content is no longer the reader's: every page would be refused alike -->
    <template v-if="pages && !hidden">
      <p class="source__where">
        {{
          printed
            ? t("documents.tree.source.printedPage", { page, pages, printed })
            : t("documents.tree.source.page", { page, pages })
        }}
      </p>
      <PagePicker :page="page" :pages="pages" @go="(to) => emit('go', to)" />
      <p v-if="cited.length" class="source__note">{{ t("documents.tree.source.citedNote") }}</p>
    </template>
    <AnchorPickBar
      v-if="picking && shown"
      :count="picked.size"
      :page="page"
      @take="give(take())"
      @not-found="give(encodeAnchor({ page }))"
    />
    <!-- quiet: the move is said once the page shows -->
    <LoadingState v-if="pending" quiet />
    <EmptyState
      v-else-if="pastEnd"
      :level="3"
      :title="t('conversionPage.noPageTitle')"
      :body="pages ? t('conversionPage.noPageBody', { pages }) : undefined"
    >
      <button type="button" class="btn btn-sm secondary" @click="emit('go', 1)">
        {{ t("conversionPage.firstPage") }}
      </button>
    </EmptyState>
    <EmptyState
      v-else-if="hidden"
      :level="3"
      :title="t('conversionPage.hiddenTitle')"
      :body="t('refusals.file_hidden')"
    />
    <ErrorState
      v-else-if="failure"
      :message="failure.text"
      :reason="failure.reason"
      :explanation="failure.explanation"
      @retry="load({ moved: true })"
    />
    <EmptyState
      v-else-if="shown && !shown.blocks.length && !shown.continued.length"
      :level="3"
      :title="t('conversionPage.emptyTitle')"
      :body="t('conversionPage.emptyBody')"
    />
    <BlockList
      v-else-if="shown"
      :blocks="shown.blocks"
      :continued="shown.continued"
      :page="shown.page"
      :cited="citedBlocks"
      :picking="!!picking"
      :picked="picked"
      @toggle="toggle"
    />
    <!-- always in the page, so the first move is read out -->
    <p class="visually-hidden" role="status">{{ status }}</p>
  </section>
</template>

<style scoped>
.source {
  display: grid;
  gap: var(--space-1);
  align-content: start;
}

.source__where,
.source__note {
  margin: 0;
  color: var(--text-muted);
  font-size: var(--step--1);
}
</style>
