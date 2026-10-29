<script setup lang="ts">
/**
 * The source beside a row (plan M1 9.9, Paket 9c J9): a page of the conversion the document was read off
 * (GET …/blocks), the blocks the row's anchors name marked (BlockList), and the pager to any other page.
 * Which page shows is the view's, which keeps it in the address; this only asks for one. The latest page
 * asked for counts: one a later one overtook is dropped. Why it shows none - the content no longer the
 * reader's, a page past the end, a failed reading - it says, with a retry.
 */
import { computed, ref, useId, watch } from "vue";

import { getDocumentBlocks, type DocumentPage } from "@/api";
import BlockList from "@/components/BlockList.vue";
import EmptyState from "@/components/EmptyState.vue";
import ErrorState from "@/components/ErrorState.vue";
import LoadingState from "@/components/LoadingState.vue";
import PagePicker from "@/components/PagePicker.vue";
import { t } from "@/i18n/de";
import { failureNotice, type Notice } from "@/notice";

const props = defineProps<{ documentId: string; page: number; cited: string[] }>();
const emit = defineEmits<{ go: [page: number] }>();

const headingId = useId();
const shown = ref<DocumentPage | null>(null);
const failure = ref<Notice | null>(null);
const pending = ref(false);
const citedBlocks = computed(() => new Set(props.cited));
const where = computed(() => {
  if (!shown.value) return "";
  const { page, pages, printed_page: printed } = shown.value;
  return printed
    ? t("documents.tree.source.printedPage", { page, pages, printed })
    : t("documents.tree.source.page", { page, pages });
});
let generation = 0;

async function load(): Promise<void> {
  const mine = ++generation;
  pending.value = true;
  failure.value = null;
  try {
    const found = await getDocumentBlocks(props.documentId, props.page);
    if (mine !== generation) return;
    shown.value = found;
  } catch (error) {
    if (mine !== generation) return;
    shown.value = null;
    failure.value = failureNotice(error, t("documents.tree.source.loadFailed"));
  } finally {
    if (mine === generation) pending.value = false;
  }
}

watch(() => [props.documentId, props.page], load, { immediate: true });
</script>

<template>
  <section class="source" :aria-labelledby="headingId">
    <h2 :id="headingId">{{ t("documents.tree.source.heading") }}</h2>
    <template v-if="shown">
      <p class="source__where">{{ where }}</p>
      <PagePicker :page="shown.page" :pages="shown.pages" @go="(to) => emit('go', to)" />
      <p v-if="cited.length" class="source__note">{{ t("documents.tree.source.citedNote") }}</p>
    </template>
    <LoadingState v-if="pending && !shown && !failure" />
    <ErrorState
      v-else-if="failure"
      :message="failure.text"
      :reason="failure.reason"
      :explanation="failure.explanation"
      @retry="load"
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
    />
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
