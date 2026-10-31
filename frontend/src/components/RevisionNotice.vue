<script setup lang="ts">
/**
 * What revision a document is, at the top of its page (plan M1 9.10, Paket 9d1 N7; after the old app's
 * FrozenRunNotice): frozen - when and as which revision, that it changes no more - with "Als Entwurf kopieren" for an
 * editor (documentRevision.ts): copied, the copy's page opens and says so once (`copied`); a draft open already is
 * named with the way to it where the server names it; a document no longer frozen is read again (`changed`); another
 * refusal said. A draft copy says which revision it copies, with the way to it, and what is to do. Neither, no notice.
 * The page sends the keyboard here once the document is frozen (`focus`): a region named by its first line.
 */
import { computed, nextTick, onMounted, ref, useId } from "vue";
import { RouterLink } from "vue-router";

import type { CurriculumDocument } from "@/api";
import AppIcon from "@/components/AppIcon.vue";
import NoticeText from "@/components/NoticeText.vue";
import { copy } from "@/documentRevision";
import { momentFormat, t } from "@/i18n/de";
import type { Notice } from "@/notice";
import { refusalText } from "@/refusals";
import { router } from "@/router";
import { isEditor } from "@/session";

const props = withDefaults(defineProps<{ document: CurriculumDocument; copied?: boolean }>(), { copied: false });
const emit = defineEmits<{ changed: [] }>();

const textId = useId();
const labelId = useId();
const root = ref<HTMLElement | null>(null);
const busy = ref(false);
const problem = ref<Notice | null>(null);
// the draft open already, where the server named it
const openDraft = ref<string | null>(null);
const status = ref("");

const frozenAt = computed(() => props.document.frozen_at);
// a copy frozen in its turn is said as frozen: the template asks that first
const original = computed(() => props.document.copy_of);

function refused(text: string | null): void {
  problem.value = { text: text ?? t("documents.page.revision.copyFailed"), failed: true };
}

async function copyIt(): Promise<void> {
  if (busy.value) return; // the button stays focusable while busy, so it can be pressed again
  busy.value = true;
  problem.value = null;
  openDraft.value = null;
  const done = await copy(props.document.id);
  busy.value = false;
  switch (done.outcome) {
    case "copied":
      await router.push({ name: "document", params: { id: done.document.id }, state: { copied: true } });
      return;
    case "open":
      openDraft.value = done.documentId;
      return refused(refusalText("draft_open"));
    case "stale":
      emit("changed");
      return;
    case "failed":
      problem.value = done.problem;
      return;
    default:
      refused(refusalText(done.code));
  }
}

onMounted(async () => {
  if (!props.copied) return;
  await nextTick(); // the region is in the page: a change of its text is heard
  status.value = t("documents.page.revision.copied");
});

defineExpose({ focus: () => root.value?.focus() });
</script>

<template>
  <!-- tabindex -1: where the keyboard goes once the document is frozen -->
  <div
    v-if="frozenAt || original"
    ref="root"
    class="page-notice revision-notice"
    role="region"
    :aria-labelledby="labelId"
    tabindex="-1"
  >
    <template v-if="frozenAt">
      <div class="page-notice__row">
        <p :id="textId" class="page-notice__text">
          <strong :id="labelId">{{
            t("documents.page.revision.frozen", { date: momentFormat.format(new Date(frozenAt)), revision: document.revision })
          }}</strong>
          {{ t("documents.page.revision.frozenText") }}
        </p>
        <!-- aria-disabled, not disabled: a disabled button drops the focus it holds -->
        <button
          v-if="isEditor()"
          type="button"
          class="btn secondary btn-sm"
          data-test="copy"
          :aria-describedby="textId"
          :aria-disabled="busy || undefined"
          @click="copyIt"
        >
          {{ t("documents.page.revision.copy") }}
        </button>
      </div>
      <p v-if="document.iri" class="page-notice__text revision-notice__iri">
        {{ t("documents.page.revision.iri", { iri: document.iri }) }}
      </p>
      <p v-if="problem" class="page-notice__failure" role="alert">
        <AppIcon name="warning" /> <NoticeText :notice="problem" />
        <template v-if="openDraft">
          {{ " " }}
          <RouterLink data-test="open-draft" :to="{ name: 'document', params: { id: openDraft } }">
            {{ t("documents.page.revision.toDraft") }}
          </RouterLink>
        </template>
      </p>
    </template>
    <p v-else-if="original" class="page-notice__text">
      <strong :id="labelId">{{ t("documents.page.revision.draft", { revision: document.revision - 1 }) }}</strong>
      {{ t("documents.page.revision.draftText") }}
      <RouterLink data-test="copy-of" :to="{ name: 'document', params: { id: original } }">
        {{ t("documents.page.revision.toOriginal") }}
      </RouterLink>
    </p>
    <!-- in the page with the notice, so a screen reader hears what is said once it has mounted -->
    <p class="visually-hidden" role="status">{{ status }}</p>
  </div>
</template>

<style scoped>
.revision-notice {
  max-width: var(--reading-width);
}

/* An IRI is one long word: it breaks rather than pushing the page sideways at 320px. */
.revision-notice__iri {
  overflow-wrap: anywhere;
}
</style>
