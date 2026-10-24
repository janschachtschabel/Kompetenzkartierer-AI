<script setup lang="ts">
/**
 * The conversion of an entry's file into blocks (X0), on the entry's page: whether there is one,
 * how far it is while its job runs, what it found or why it failed - and the way to start it, to
 * start it again, and to its blocks. Only a PDF is converted so far, so another file is not asked
 * about; a file only the editors may read is said to be theirs, without a start. What happens
 * while the reader is on the page - started, done, failed - is announced in a region that is
 * there from the start, once: the job's progress is shown, not announced; a state found on
 * arrival is shown, not announced either.
 *
 * The conversion belongs to the file, its job to whoever started it: another account holding
 * the same file, an editor, the reader of an entry of no account gets no job named, or one that
 * answers them 404 (app/api/jobs.py). The panel then asks after the conversion itself, as a job
 * is asked after (jobWatch.ts), until it is no longer waiting. A conversion done is where an
 * extraction starts (ExtractionStart).
 */
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from "vue";

import { ApiError, askConversion, CONVERTED_MIME, getConversion, type Conversion } from "@/api";
import AppIcon from "@/components/AppIcon.vue";
import ConversionSummary from "@/components/ConversionSummary.vue";
import ErrorState from "@/components/ErrorState.vue";
import ExtractionStart from "@/components/ExtractionStart.vue";
import JobProgress from "@/components/JobProgress.vue";
import LoadingState from "@/components/LoadingState.vue";
import NoticeText from "@/components/NoticeText.vue";
import { conversionFailureText } from "@/conversionWords";
import { focusIsFree } from "@/focusRescue";
import { t } from "@/i18n/de";
import { askWithBackoff, type JobWatch } from "@/jobWatch";
import { sayAnew } from "@/liveRegion";
import { failureNotice, type Notice } from "@/notice";

/** `country`: the entry's Land, chosen at the start of an extraction. */
const props = defineProps<{ sourceId: string; mime: string; country?: string | null }>();

const convertible = computed(() => props.mime === CONVERTED_MIME);
const conversion = ref<Conversion | null>(null);
const loading = ref(convertible.value);
/** None was asked for yet (404 no_conversion). */
const none = ref(false);
/** The file is the editors' alone (403 file_hidden). */
const hidden = ref(false);
/** The state did not load. */
const failure = ref<Notice | null>(null);
/** The start was refused; said beside the button, which stays. */
const refusal = ref<Notice | null>(null);
const busy = ref(false);
const status = ref("");
const heading = ref<HTMLElement | null>(null);
const section = ref<HTMLElement | null>(null);
/** The job that answered it is gone - another's, or one this reader may not follow. */
const lostJob = ref<string | null>(null);
// The latest answer counts: a reading asked for before a start is older than the start's answer
let generation = 0;
let following: JobWatch | null = null;

const failed = computed(() => conversion.value?.status === "failed");
/** Failed by a cancel: the reader's own doing, said plainly - not as a failure. */
const stopped = computed(() => failed.value && conversion.value?.error_code === "cancelled");
/** Waiting with no job this reader can follow: the conversion itself is asked after. */
const unfollowed = computed(() => {
  const state = conversion.value;
  return state?.status === "pending" && (!state.job_id || state.job_id === lostJob.value);
});
const startable = computed(() => none.value || failed.value);

function refusedAs(error: unknown, status: number, code: string): boolean {
  return error instanceof ApiError && error.status === status && error.code === code;
}

/** What the page says of a conversion that came to its end while the reader was there. */
function outcome(state: Conversion): string {
  if (state.status === "done") return t("conversions.done", { pages: state.pages ?? 0 });
  if (state.status === "failed" && state.error_code === "cancelled") return t("conversions.stopped");
  if (state.status === "failed") return `${t("conversions.failed")} ${conversionFailureText(state.error_code)}`;
  return "";
}

function say(message: string): void {
  if (message) status.value = sayAnew(status.value, message);
}

/** The conversion as the server has it; `announce`: its job just ended, and how it ended is said. */
async function load({ announce = false } = {}): Promise<void> {
  const mine = ++generation;
  // the job's view goes with its state: the keyboard that rested in it goes to the section's heading
  const focusWasHere = announce && (section.value?.contains(document.activeElement) ?? false);
  loading.value = true;
  failure.value = null;
  try {
    const found = await getConversion(props.sourceId);
    if (mine !== generation) return;
    conversion.value = found;
    none.value = false;
    hidden.value = false;
    if (announce) say(outcome(found));
    if (focusWasHere) {
      await nextTick();
      if (focusIsFree()) heading.value?.focus();
    }
  } catch (error) {
    if (mine !== generation) return;
    conversion.value = null;
    none.value = refusedAs(error, 404, "no_conversion");
    hidden.value = refusedAs(error, 403, "file_hidden");
    if (!none.value && !hidden.value) failure.value = failureNotice(error, t("conversions.loadFailed"));
  } finally {
    if (mine === generation) loading.value = false;
  }
}

async function start(): Promise<void> {
  if (busy.value) return; // the button stays focusable while busy, so it can be pressed again
  const from = document.activeElement;
  busy.value = true;
  refusal.value = null;
  try {
    const started = await askConversion(props.sourceId);
    generation += 1;
    loading.value = false;
    conversion.value = started;
    none.value = false;
    // asked anew, a conversion another account started meanwhile may come back done
    say(started.status === "pending" ? t("conversions.started") : outcome(started));
    // the button went with the state it belonged to: the keyboard goes to the section's heading,
    // where it still rests on the button, or nowhere
    await nextTick();
    if (document.activeElement === from || focusIsFree()) heading.value?.focus();
  } catch (error) {
    refusal.value = failureNotice(error, t("conversions.startFailed"));
  } finally {
    busy.value = false;
  }
}

/** Asks after the conversion until it no longer waits, or a job this reader can follow takes it on. */
function follow(): JobWatch {
  return askWithBackoff(async (wanted) => {
    try {
      const found = await getConversion(props.sourceId);
      if (!wanted()) return false;
      conversion.value = found; // done, failed, or a job to follow: unfollowed ends the asking
      if (found.status !== "pending") say(outcome(found));
      return found.status === "pending";
    } catch (error) {
      if (!wanted()) return false;
      if (!(error instanceof ApiError) || error.status >= 500) return true; // the next question follows
      void load(); // gone or refused meanwhile: the section shows why
      return false;
    }
  });
}

watch(unfollowed, (asking) => {
  following?.stop();
  following = asking ? follow() : null;
});

onMounted(() => {
  if (convertible.value) void load();
});

onUnmounted(() => following?.stop());
</script>

<template>
  <section ref="section" class="conversion" aria-labelledby="source-conversion">
    <!-- tabindex -1: where the keyboard goes once the button it pressed went with its state -->
    <h2 id="source-conversion" ref="heading" tabindex="-1">{{ t("conversions.heading") }}</h2>
    <p v-if="!convertible" class="conversion__note">{{ t("refusals.not_pdf") }}</p>
    <LoadingState v-else-if="loading && !conversion" />
    <p v-else-if="hidden" class="conversion__note">{{ t("refusals.file_hidden") }}</p>
    <ErrorState
      v-else-if="failure"
      :message="failure.text"
      :reason="failure.reason"
      :explanation="failure.explanation"
      @retry="load()"
    />
    <p v-else-if="none" class="conversion__note">{{ t("conversions.intro") }}</p>
    <template v-else-if="conversion">
      <template v-if="conversion.status === 'pending'">
        <JobProgress
          v-if="conversion.job_id && !unfollowed"
          :key="conversion.job_id"
          :job-id="conversion.job_id"
          :label="t('conversions.jobLabel')"
          quiet
          @ended="load({ announce: true })"
          @gone="lostJob = conversion.job_id"
        />
        <p v-else class="conversion__note" data-test="conversion-following">{{ t("conversions.following") }}</p>
      </template>
      <template v-else-if="conversion.status === 'done'">
        <ConversionSummary :conversion="conversion" :source-id="sourceId" />
        <ExtractionStart :source-id="sourceId" :conversion-id="conversion.id" :country="country ?? null" />
      </template>
      <p v-else-if="stopped" class="conversion__note">{{ t("conversions.stopped") }}</p>
      <p v-else class="conversion__failure">
        <AppIcon name="warning" />
        <span>{{ t("conversions.failed") }} {{ conversionFailureText(conversion.error_code) }}</span>
      </p>
    </template>
    <div v-if="startable && !loading" class="conversion__start">
      <p v-if="refusal" class="field__error" role="alert"><AppIcon name="warning" /> <NoticeText :notice="refusal" /></p>
      <!-- aria-disabled, not disabled: a disabled button drops the focus it holds -->
      <button
        type="button"
        class="btn primary"
        data-test="conversion-start"
        :aria-disabled="busy || undefined"
        @click="start"
      >
        {{ failed ? t("states.retry") : t("conversions.start") }}
      </button>
    </div>
    <!-- always in the page, so a screen reader hears each change of its text -->
    <p class="visually-hidden" role="status" data-test="conversion-status">{{ status }}</p>
  </section>
</template>

<style scoped>
.conversion__note {
  max-width: var(--reading-width);
  color: var(--text-muted);
  margin: 0 0 var(--space-2);
}

/* Words and the sign together: the colour is the second signal, not the only one (SC 1.4.1). */
.conversion__failure {
  display: flex;
  gap: var(--space-1);
  max-width: var(--reading-width);
  margin: 0 0 var(--space-2);
  color: var(--danger);
}

.conversion__start {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: var(--space-1);
}
</style>
