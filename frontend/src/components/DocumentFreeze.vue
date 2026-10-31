<script setup lang="ts">
/**
 * Freezing a document, on its page (plan M1 9.10, Paket 9d1 N6; documentRevision.ts): offered to an editor while it
 * is open. Asked first (FreezeDialog); where its findings name violations, asked again by their count, a yes taking
 * them. Frozen, the document goes to the page (`frozen`), which reads it and says so. What is missing for its IRI is
 * named item by item; a check owed is said with the way to the tree, where it is checked; a document closed
 * meanwhile is said and read again (`changed`); another refusal said. While it freezes nothing more is asked.
 */
import { computed, ref } from "vue";
import { RouterLink } from "vue-router";

import type { CurriculumDocument } from "@/api";
import AppIcon from "@/components/AppIcon.vue";
import ConfirmDialog from "@/components/ConfirmDialog.vue";
import FreezeDialog from "@/components/FreezeDialog.vue";
import NoticeText from "@/components/NoticeText.vue";
import { freeze, missingWords } from "@/documentRevision";
import { t } from "@/i18n/de";
import type { Notice } from "@/notice";
import { refusalText } from "@/refusals";
import { isEditor } from "@/session";

const props = defineProps<{ document: CurriculumDocument }>();
const emit = defineEmits<{ frozen: [document: CurriculumDocument]; changed: [] }>();

const asking = ref<"freeze" | "violations" | null>(null);
const count = ref(0);
const busy = ref(false);
const problem = ref<Notice | null>(null);
// a check owed: the way to the tree goes with the words
const owed = ref(false);

const offered = computed(() => isEditor() && props.document.frozen_at === null);

function ask(): void {
  if (!busy.value) asking.value = "freeze"; // the button stays focusable while busy, so it can be pressed again
}

async function run(acceptViolations: boolean): Promise<void> {
  asking.value = null;
  busy.value = true;
  problem.value = null;
  owed.value = false;
  const done = await freeze(props.document.id, acceptViolations);
  busy.value = false;
  switch (done.outcome) {
    case "frozen":
      emit("frozen", done.document);
      return;
    case "violations":
      count.value = done.count;
      asking.value = "violations";
      return;
    case "incomplete": {
      const missing = missingWords(done.missing);
      const text = missing.length
        ? t("documents.page.freeze.incomplete", { missing: missing.join(", ") })
        : (refusalText("incomplete") ?? t("documents.page.freeze.failed"));
      problem.value = { text, failed: true };
      return;
    }
    case "owed":
      owed.value = true;
      problem.value = { text: refusalText("check_owed") ?? t("documents.page.freeze.failed"), failed: true };
      return;
    case "failed":
      problem.value = done.problem;
      return;
    default:
      problem.value = { text: refusalText(done.code) ?? t("documents.page.freeze.failed"), failed: true };
      if (done.outcome === "closed") emit("changed");
  }
}
</script>

<template>
  <section v-if="offered" class="freeze" aria-labelledby="document-freeze">
    <h2 id="document-freeze">{{ t("documents.page.freeze.heading") }}</h2>
    <p class="freeze__intro">{{ t("documents.page.freeze.intro") }}</p>
    <p v-if="problem" class="field__error freeze__problem" role="alert">
      <AppIcon name="warning" /> <NoticeText :notice="problem" />
      <template v-if="owed">
        {{ " " }}
        <RouterLink data-test="freeze-tree" :to="{ name: 'documentTree', params: { id: document.id } }">
          {{ t("documents.page.freeze.toTree") }}
        </RouterLink>
      </template>
    </p>
    <!-- aria-disabled, not disabled: a disabled button drops the focus it holds -->
    <button type="button" class="btn primary" data-test="freeze" :aria-disabled="busy || undefined" @click="ask">
      {{ t("documents.page.freeze.button") }}
    </button>
    <FreezeDialog
      v-if="asking === 'freeze'"
      :title="document.title || t('documents.untitled')"
      :revision="document.revision"
      @confirm="run(false)"
      @cancel="asking = null"
    />
    <ConfirmDialog
      v-if="asking === 'violations'"
      :title="t('documents.page.freeze.violationsTitle')"
      :message="t('documents.page.freeze.violationsMessage', { count })"
      :confirm-label="t('documents.page.freeze.violationsConfirm')"
      @confirm="run(true)"
      @cancel="asking = null"
    />
  </section>
</template>

<style scoped>
.freeze {
  display: grid;
  gap: var(--space-2);
  justify-items: start;
}

.freeze h2,
.freeze__intro,
.freeze__problem {
  margin: 0;
}

.freeze__intro {
  max-width: var(--reading-width);
}
</style>
