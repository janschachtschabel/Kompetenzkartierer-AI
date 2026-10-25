<script setup lang="ts">
/**
 * The owner's repair of a document (plan M1 8b, F8), offered beside its findings where they name work
 * packages a repair would ask again and no job of the document waits or runs (`busy`, the page's):
 * X6 asks those again, X5 checks anew. Started here, followed under "Extraktion"
 * (DocumentExtraction.vue) once the page has read the document again (`started`). That it started
 * is said in a region there from the start; a refusal beside the button, which stays.
 */
import { computed, ref } from "vue";

import { startRepair, type Job } from "@/api";
import AppIcon from "@/components/AppIcon.vue";
import NoticeText from "@/components/NoticeText.vue";
import { t } from "@/i18n/de";
import { sayAnew } from "@/liveRegion";
import { failureNotice, type Notice } from "@/notice";

const props = defineProps<{ documentId: string; repairable: string[]; busy: boolean }>();
const emit = defineEmits<{ started: [job: Job] }>();

const starting = ref(false);
const failure = ref<Notice | null>(null);
const status = ref("");

const offered = computed(() => props.repairable.length > 0 && !props.busy);

async function start(): Promise<void> {
  if (starting.value) return; // the button stays focusable while busy, so it can be pressed again
  starting.value = true;
  failure.value = null;
  try {
    const job = await startRepair(props.documentId);
    status.value = sayAnew(status.value, t("documents.findings.repair.started"));
    emit("started", job);
  } catch (error) {
    failure.value = failureNotice(error, t("documents.findings.repair.failed"));
  } finally {
    starting.value = false;
  }
}
</script>

<template>
  <div class="repair">
    <template v-if="offered">
      <p class="repair__offer" data-test="repair-offer">
        {{ t("documents.findings.repair.offer", { count: repairable.length }) }}
      </p>
      <p v-if="failure" class="field__error" role="alert">
        <AppIcon name="warning" /> <NoticeText :notice="failure" />
      </p>
      <!-- aria-disabled, not disabled: a disabled button drops the focus it holds -->
      <button
        type="button"
        class="btn primary"
        data-test="repair-start"
        :aria-disabled="starting || undefined"
        @click="start"
      >
        {{ t("documents.findings.repair.start") }}
      </button>
    </template>
    <!-- always in the page, so a screen reader hears each change of its text -->
    <p class="visually-hidden" role="status" data-test="repair-status">{{ status }}</p>
  </div>
</template>

<style scoped>
.repair {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: var(--space-1);
  margin-block-start: var(--space-3);
}

.repair__offer {
  max-width: var(--reading-width);
  margin: 0;
}
</style>
