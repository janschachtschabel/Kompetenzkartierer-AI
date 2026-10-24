<script setup lang="ts">
/**
 * One job the page started, followed until it ends (jobWatch.ts): its state as
 * a pill and in words, why it failed, and that the server is not answering
 * while it is not. Each change of state is announced in a region that is there
 * from the start - one created with its first text is often not read - and only
 * a change: the same state again says nothing new.
 *
 * A job waiting or running can be cancelled from here, after a question (plan M1
 * 7a): a waiting one ends at once, a running one stops at its worker's next
 * heartbeat, a few seconds later at most even where its work does not stop by
 * itself. Until it has ended the page says the stop is asked for - announced also
 * where the page around says the job's states itself (`quiet`): the stop is the
 * reader's own doing. How long a job has waited or run tells whether to.
 */
import { computed, nextTick, onMounted, onUnmounted, ref, watch as watchValue } from "vue";

import { ApiError, cancelJob, type Job, type JobProgressNote, type JobStatus } from "@/api";
import { isolate } from "@/bidi";
import ConfirmDialog from "@/components/ConfirmDialog.vue";
import { focusIsFree } from "@/focusRescue";
import { t } from "@/i18n/de";
import { jobFailureText } from "@/jobMessages";
import { progressText } from "@/jobProgress";
import { hasEnded, watchJob, type JobGone, type JobWatch } from "@/jobWatch";

const props = defineProps<{
  jobId: string;
  /** What the job works on, as the page names it. */
  label: string;
  /**
   * Its states shown and not announced: the page around it says how the job ended, once, in its
   * words. That the server does not answer is still said - only this can tell the progress stalls.
   */
  quiet?: boolean;
}>();
// progress: each new one the job reports, for a page that follows more than the job (DocumentView)
const emit = defineEmits<{ ended: [job: Job]; gone: [why: JobGone]; progress: [progress: JobProgressNote] }>();

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
const gone = ref<JobGone | null>(null);
// the cancel: its question open, its request on the way, why it was not taken
const asking = ref(false);
const cancelling = ref(false);
const cancelFailure = ref("");
// the cancel taken: an answer to a question asked before it does not undo it
const asked = ref(false);
// the stop asked for is said once: by the keyboard landing on its note, else in the region; the
// job's end likewise, by the keyboard landing on its line
const noteSays = ref(false);
const lineSays = ref(false);
// when the page last heard of the job - every 8 seconds at most while it is open: how long it
// has waited or run is counted to then
const now = ref(Date.now());
const root = ref<HTMLElement | null>(null);
const line = ref<HTMLElement | null>(null);
const askedNote = ref<HTMLElement | null>(null);
const cancelButton = ref<HTMLElement | null>(null);
let watch: JobWatch | null = null;
// the page is told of the end once, whether a question or the cancel's answer brought it
let endedSaid = false;
// the progress the page was told of last, as the server wrote it
let progressSaid = "";

// a job just started waits for a worker until the server says otherwise
const status = computed<JobStatus>(() => job.value?.status ?? "queued");
const failure = computed(() => (status.value === "failed" ? jobFailureText(job.value?.error_code ?? null) : ""));
const goneText = computed(() => (gone.value ? t(`jobs.goneReasons.${gone.value}`) : ""));
// How far the job has come, shown and not announced: a check counts its addresses one by one
const progressLine = computed(() => progressText(job.value?.progress));
const open = computed(() => !gone.value && job.value !== null && !hasEnded(status.value));
const cancellable = computed(() => open.value && !asked.value && job.value?.cancel_requested === false);
const cancelAsked = computed(() => open.value && (asked.value || job.value?.cancel_requested === true));
// in whole minutes and hours; the server's clock and the page's may differ a little
const runtimeText = computed(() => {
  const state = job.value;
  if (state?.status === "running" && state.started_at) return lasted("running", state.started_at);
  // one handed back waits again: since when it was made says nothing of how long it waits
  if (state?.status === "queued" && open.value) {
    return state.attempts > 0 ? t("jobs.waitingAgain") : lasted("waiting", state.created_at);
  }
  return "";
});

function lasted(how: "running" | "waiting", since: string): string {
  const minutes = Math.floor((now.value - Date.parse(since)) / 60_000);
  if (minutes < 1) return t(`jobs.${how}JustNow`);
  if (minutes < 60) return t(`jobs.${how}For`, { minutes });
  const hours = Math.floor(minutes / 60);
  return minutes % 60
    ? t(`jobs.${how}ForHours`, { hours, minutes: minutes % 60 })
    : t(`jobs.${how}ForHoursOnly`, { hours });
}
// Each change of what the page shows, and only a change: the same state again reads the same.
const announcement = computed(() => {
  const label = isolate(props.label);
  if (trouble.value) return t("jobs.announce", { label, status: t("jobs.trouble") });
  if (lineSays.value) return "";
  const stopSaid = cancelAsked.value && !noteSays.value;
  if (props.quiet) return stopSaid ? t("jobs.cancel.requested") : "";
  if (goneText.value) return t("jobs.announce", { label, status: goneText.value });
  if (!job.value) return ""; // nothing to say before the first answer
  const line = t("jobs.announce", { label, status: t(`jobs.status.${status.value}`) });
  if (failure.value) return `${line}. ${failure.value}`;
  return stopSaid ? `${line}. ${t("jobs.cancel.requested")}` : line;
});

// The job's end takes its note, its button, its question with it: the keyboard that rested on
// one stays at the job, where nothing took it meanwhile; a question still open asks about nothing.
// Quiet, the page around says the end and takes the keyboard to its own heading.
watchValue(open, async (still) => {
  if (still) return;
  const active = document.activeElement;
  const inside = root.value?.contains(active) ?? false;
  asking.value = false;
  if (!inside || props.quiet) return;
  lineSays.value = active !== line.value;
  await nextTick();
  if (lineSays.value && focusIsFree()) line.value?.focus();
  lineSays.value &&= document.activeElement === line.value;
});

function ended(state: Job): void {
  if (endedSaid) return;
  endedSaid = true;
  emit("ended", state);
}

function askCancel(): void {
  if (!cancelling.value) asking.value = true;
}

async function cancel(): Promise<void> {
  asking.value = false;
  cancelling.value = true;
  cancelFailure.value = "";
  try {
    // the state it answers is the job's from now; the watch goes on until it has ended
    const answer = await cancelJob(props.jobId);
    if (endedSaid && !hasEnded(answer.status)) return; // the end a question brought stands
    // the keyboard rests on the button that goes with this answer, or nowhere: it goes to what
    // says how the job stands now - the note reads the stop out, the region need not say it too
    const leaving = focusIsFree() || document.activeElement === cancelButton.value;
    const endsNow = hasEnded(answer.status);
    noteSays.value = leaving && !endsNow;
    lineSays.value = leaving && endsNow && !props.quiet;
    asked.value = true;
    job.value = answer;
    if (endsNow) {
      // a waiting job ended at once: the page hears now, and no answer asked before undoes it
      watch?.stop();
      ended(answer);
    }
    await nextTick();
    if (leaving && focusIsFree() && (noteSays.value || lineSays.value)) (askedNote.value ?? line.value)?.focus();
    // where the keyboard did not get there, the region says it after all
    noteSays.value &&= document.activeElement === askedNote.value;
    lineSays.value &&= document.activeElement === line.value;
  } catch (error) {
    cancelFailure.value = cancelRefusal(error);
  } finally {
    cancelling.value = false;
  }
}

function cancelRefusal(error: unknown): string {
  if (error instanceof ApiError && error.status === 409) return t("jobs.cancel.ended");
  if (error instanceof ApiError && error.status === 404) return t("jobs.cancel.gone");
  return t("jobs.cancel.failed");
}

onMounted(() => {
  watch = watchJob(props.jobId, {
    onState: (state) => {
      job.value = state;
      now.value = Date.now();
      trouble.value = false;
      const progress = state.progress ? JSON.stringify(state.progress) : "";
      if (state.progress && progress !== progressSaid) emit("progress", state.progress);
      progressSaid = progress;
      if (hasEnded(state.status)) ended(state);
    },
    onGone: (why) => {
      gone.value = why;
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
  <div ref="root" class="job">
    <!-- tabindex -1: where the keyboard goes once what it rested on went with the job's state -->
    <p ref="line" class="job__line" tabindex="-1">
      <span v-if="!gone" class="status-badge" :class="TONE[status]">{{ t(`jobs.status.${status}`) }}</span>
      <bdi class="job__label">{{ label }}</bdi>
    </p>
    <p v-if="progressLine" class="job__progress">{{ progressLine }}</p>
    <p v-if="runtimeText" class="job__progress" data-test="job-runtime">{{ runtimeText }}</p>
    <p v-if="failure" class="job__failure">{{ failure }}</p>
    <p v-if="cancelAsked" ref="askedNote" class="job__note" tabindex="-1" data-test="job-cancel-asked">
      {{ t("jobs.cancel.requested") }}
    </p>
    <p v-if="gone" class="job__note">{{ goneText }}</p>
    <p v-else-if="trouble" class="job__note">{{ t("jobs.trouble") }}</p>
    <div v-if="cancellable || cancelFailure" class="job__actions">
      <!-- aria-disabled, not disabled: a disabled button drops the focus it holds -->
      <button
        v-if="cancellable"
        ref="cancelButton"
        type="button"
        class="btn secondary"
        data-test="job-cancel"
        :aria-label="t('jobs.cancel.name', { label })"
        :aria-disabled="cancelling || undefined"
        @click="askCancel"
      >
        {{ t("jobs.cancel.button") }}
      </button>
      <p v-if="cancelFailure" class="job__failure" role="alert" data-test="job-cancel-failed">{{ cancelFailure }}</p>
    </div>
    <p class="visually-hidden" role="status">{{ announcement }}</p>
    <ConfirmDialog
      v-if="asking"
      :title="t('jobs.cancel.title')"
      :message="t('jobs.cancel.message', { label })"
      :confirm-label="t('jobs.cancel.confirm')"
      :cancel-label="t('jobs.cancel.keep')"
      @confirm="cancel"
      @cancel="asking = false"
    />
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

.job__progress {
  margin: var(--space-0) 0 0;
  font-size: var(--step--1);
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

.job__actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-1);
  margin: var(--space-1) 0 0;
}
</style>
