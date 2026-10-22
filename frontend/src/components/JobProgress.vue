<script setup lang="ts">
/**
 * One job the page started, followed until it ends (jobWatch.ts): its state as
 * a pill and in words, why it failed, and that the server is not answering
 * while it is not. Each change of state is announced in a region that is there
 * from the start - one created with its first text is often not read - and only
 * a change: the same state again says nothing new.
 */
import { computed, onMounted, onUnmounted, ref } from "vue";

import type { Job, JobStatus } from "@/api";
import { t } from "@/i18n/de";
import { jobFailureText } from "@/jobMessages";
import { hasEnded, watchJob, type JobGone, type JobWatch } from "@/jobWatch";

const props = defineProps<{
  jobId: string;
  /** What the job works on, as the page names it. */
  label: string;
}>();
const emit = defineEmits<{ ended: [job: Job]; gone: [why: JobGone] }>();

// The pill by what the state means (style.css, .status-badge); the word in it carries the meaning
const TONE: Record<JobStatus, string> = {
  queued: "neutral",
  running: "info",
  done: "success",
  failed: "error",
  cancelled: "warning",
};

const job = ref<Job | null>(null);
const trouble = ref(false);
const gone = ref(false);
let watch: JobWatch | null = null;

// a job just started waits for a worker until the server says otherwise
const status = computed<JobStatus>(() => job.value?.status ?? "queued");
const failure = computed(() => (status.value === "failed" ? jobFailureText(job.value?.error_code ?? null) : ""));
const announcement = computed(() => {
  if (gone.value) return t("jobs.announce", { label: props.label, status: t("jobs.gone") });
  if (!job.value) return ""; // nothing to say before the first answer
  const line = t("jobs.announce", { label: props.label, status: t(`jobs.status.${status.value}`) });
  return failure.value ? `${line} ${failure.value}` : line;
});

onMounted(() => {
  watch = watchJob(props.jobId, {
    onState: (state) => {
      job.value = state;
      trouble.value = false;
      if (hasEnded(state.status)) emit("ended", state);
    },
    onGone: (why) => {
      gone.value = true;
      trouble.value = false;
      emit("gone", why);
    },
    onTrouble: () => {
      trouble.value = true;
    },
  });
});

onUnmounted(() => watch?.stop());
</script>

<template>
  <div class="job">
    <p class="job__line">
      <span v-if="!gone" class="status-badge" :class="TONE[status]">{{ t(`jobs.status.${status}`) }}</span>
      <bdi class="job__label">{{ label }}</bdi>
    </p>
    <p v-if="failure" class="job__failure">{{ failure }}</p>
    <p v-if="gone" class="job__note">{{ t("jobs.gone") }}</p>
    <p v-else-if="trouble" class="job__note">{{ t("jobs.trouble") }}</p>
    <p class="visually-hidden" role="status">{{ announcement }}</p>
  </div>
</template>

<style scoped>
.job__line {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-1);
  margin: 0;
}

/* A long title breaks rather than pushing the page sideways at 320px. */
.job__label {
  overflow-wrap: anywhere;
}

.job__failure {
  margin: var(--space-0) 0 0;
  color: var(--danger);
  font-size: var(--step--1);
}

.job__note {
  margin: var(--space-0) 0 0;
  color: var(--text-muted);
  font-size: var(--step--1);
}
</style>
