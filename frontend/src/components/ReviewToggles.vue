<script setup lang="ts">
/**
 * The review status of the row chosen, to set (plan M1 9.8, Paket 9c2c M2, M3; rowReview.ts): the editors' alone,
 * where the tree is open - which the panel decides. The three statuses as toggles in a group named for it, the
 * row's own pressed and ticked, not by colour alone, and asking nothing; another sets it for this row. While it
 * sets one nothing more is asked. How it went is told by a function (`onReviewed`) with the row's key - heard
 * even where another row was chosen meanwhile -, a failure said here, where it was asked.
 */
import { computed, ref, useId } from "vue";

import AppIcon from "@/components/AppIcon.vue";
import NoticeText from "@/components/NoticeText.vue";
import type { Row, RowKey } from "@/documentTree";
import { t } from "@/i18n/de";
import type { Notice } from "@/notice";
import { reviewRow, rowStatus, type ReviewOutcome } from "@/rowReview";
import { REVIEW_STATUSES, statusIri, statusWord, type ReviewStatus } from "@/reviewStatus";

const props = defineProps<{
  row: Row;
  documentId: string;
  /** How setting it went. A prop, not an event: these toggles go with the row chosen. */
  onReviewed?: (done: Exclude<ReviewOutcome, { outcome: "failed" }>, key: RowKey) => void;
}>();

const labelId = useId();
const busy = ref(false);
const problem = ref<Notice | null>(null);
const current = computed(() => rowStatus(props.row));

async function choose(status: ReviewStatus): Promise<void> {
  if (busy.value || status === current.value) return;
  const { key } = props.row;
  busy.value = true;
  problem.value = null;
  const done = await reviewRow(props.documentId, props.row, status);
  busy.value = false;
  if (done.outcome === "failed") problem.value = done.problem;
  else props.onReviewed?.(done, key);
}
</script>

<template>
  <div class="review-toggles" role="group" :aria-labelledby="labelId">
    <span :id="labelId" class="review-toggles__label">{{ t("documents.tree.review.label") }}</span>
    <!-- aria-disabled, not disabled: a toggle keeps the keyboard while the status is set -->
    <button
      v-for="status in REVIEW_STATUSES"
      :key="status"
      type="button"
      class="btn btn-sm secondary"
      :aria-pressed="current === status ? 'true' : 'false'"
      :aria-disabled="busy || undefined"
      @click="choose(status)"
    >
      <!-- its room kept while off, so the row of toggles does not shift -->
      <span class="review-toggles__tick" aria-hidden="true"><AppIcon v-if="current === status" name="check" /></span>
      {{ statusWord(statusIri(status)) }}
    </button>
    <p v-if="problem" class="field__error review-toggles__problem" role="alert">
      <AppIcon name="warning" /> <NoticeText :notice="problem" />
    </p>
  </div>
</template>

<style scoped>
.review-toggles {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-1);
}

.review-toggles__label {
  font-weight: 600;
}

.review-toggles__tick {
  display: inline-flex;
  inline-size: 1em;
}

.review-toggles__problem {
  flex-basis: 100%;
  margin: 0;
}
</style>
