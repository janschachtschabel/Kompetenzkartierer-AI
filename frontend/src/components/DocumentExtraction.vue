<script setup lang="ts">
/**
 * A document's extraction, on its page (plan M1 7.5, 7a): the one waiting or running followed
 * and cancelled here (JobProgress), one that ended - done, failed, cancelled - started again by
 * the document's owner, going on where it stopped. Its job is named only to whom may follow it,
 * its owner and the admins (backend app/api/documents.py); another who reads the document - an
 * editor - and one whose job is gone from them read its state from the document, asked after as
 * a job is (jobWatch.ts) until it is no longer waiting or running.
 *
 * Started, ended - followed or asked after: said once in a region that is there from the start;
 * JobProgress shows its states without announcing them, the region going with it once the job
 * has ended. The page reads the document again when the extraction has moved on (`changed`),
 * and the keyboard goes to the section's heading where what it rested on went with the state it
 * belonged to. `led`: the start form led here to an extraction that ran already for the PDF.
 */
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from "vue";

import { ApiError, getDocument, startExtraction, type CurriculumDocument, type Job, type JobStatus } from "@/api";
import { isolate } from "@/bidi";
import AppIcon from "@/components/AppIcon.vue";
import JobProgress from "@/components/JobProgress.vue";
import NoticeText from "@/components/NoticeText.vue";
import { focusIsFree } from "@/focusRescue";
import { t } from "@/i18n/de";
import { jobFailureText } from "@/jobMessages";
import { askWithBackoff, hasEnded, type JobWatch } from "@/jobWatch";
import { sayAnew } from "@/liveRegion";
import { failureNotice, type Notice } from "@/notice";

const props = defineProps<{ document: CurriculumDocument; led?: boolean }>();
const emit = defineEmits<{ changed: [] }>();

/** The job a start from here gave back, followed until the page reads the document again -
 * once it has ended too, so its end shows until the document says how the extraction stands. */
const started = ref<string | null>(null);
/** The document's job that answered 404 or 403: its state is read from the document instead. */
const lost = ref<string | null>(null);
const starting = ref(false);
const startFailure = ref<Notice | null>(null);
const status = ref("");
const section = ref<HTMLElement | null>(null);
const heading = ref<HTMLElement | null>(null);
// the keyboard was in the section when the extraction moved on: it stays there once it has
let focusWasHere = false;
let asking: JobWatch | null = null;

const latest = computed(() => props.document.extraction);
const open = computed(() => latest.value !== null && !hasEnded(latest.value.status));
/** The job this reader follows: the one just started, else the document's open one, if theirs. */
const followed = computed(() => {
  if (started.value) return started.value;
  const job = latest.value?.job_id;
  return open.value && job && job !== lost.value ? job : null;
});
/** Waiting or running with no job to follow: the status the document gives, asked after. */
const unfollowed = computed(() => open.value && followed.value === null);
const label = computed(() => t("documents.page.jobLabel"));

function say(message: string): void {
  status.value = sayAnew(status.value, message);
}

function stateLine(status: JobStatus): string {
  return t("jobs.announce", { label: isolate(label.value), status: t(`jobs.status.${status}`) });
}

function outcome(job: Job): string {
  const line = stateLine(job.status);
  return job.status === "failed" ? `${line}. ${jobFailureText(job.error_code)}` : line;
}

function movedOn(): void {
  focusWasHere = section.value?.contains(document.activeElement) ?? false;
  emit("changed");
}

function onEnded(job: Job): void {
  say(outcome(job));
  movedOn();
}

/** Its job is no longer the reader's to follow: the document says how the extraction stands. */
function onGone(): void {
  lost.value = followed.value;
  started.value = null;
  movedOn();
}

async function resume(): Promise<void> {
  if (starting.value) return; // the button stays focusable while busy, so it can be pressed again
  starting.value = true;
  startFailure.value = null;
  try {
    started.value = (await startExtraction(props.document.id)).id;
    say(t("documents.page.started"));
    // the button went with the state it belonged to: the keyboard goes to the section's heading,
    // where it was left on nothing
    await nextTick();
    if (focusIsFree()) heading.value?.focus();
  } catch (error) {
    startFailure.value = failureNotice(error, t("documents.page.resumeFailed"));
  } finally {
    starting.value = false;
  }
}

/** Asks after the document until its extraction's state moves on; then the page reads it again. */
function follow(): JobWatch {
  const was = latest.value?.status;
  return askWithBackoff(async (wanted) => {
    try {
      const found = await getDocument(props.document.id);
      if (!wanted()) return false;
      if (found.extraction?.status === was) return true;
      const now = found.extraction?.status;
      if (now && hasEnded(now)) say(stateLine(now));
      movedOn();
      return false;
    } catch (error) {
      if (!wanted()) return false;
      if (!(error instanceof ApiError) || error.status >= 500) return true; // the next question follows
      movedOn(); // gone or refused meanwhile: the page shows why
      return false;
    }
  });
}

// asked after anew for each reading of the document while no job is followed: one that came
// back as it was, or after a refusal, is asked after again
watch(
  () => (unfollowed.value ? props.document : null),
  (reading) => {
    asking?.stop();
    asking = reading ? follow() : null;
  },
  { immediate: true },
);

watch(
  () => props.document,
  async () => {
    started.value = null; // the document names its latest job now
    if (!focusWasHere) return;
    focusWasHere = false;
    await nextTick();
    if (focusIsFree()) heading.value?.focus();
  },
);

onMounted(async () => {
  if (!props.led) return;
  await nextTick(); // the region is in the page: a change of its text is heard
  say(t("documents.page.ledToRunning"));
});

onUnmounted(() => asking?.stop());
</script>

<template>
  <section ref="section" aria-labelledby="document-extraction">
    <!-- tabindex -1: where the keyboard goes once what it pressed went with its state -->
    <h2 id="document-extraction" ref="heading" tabindex="-1">{{ t("documents.page.extraction") }}</h2>
    <p v-if="led" class="extraction__note" data-test="extraction-led">{{ t("documents.page.ledToRunning") }}</p>
    <JobProgress v-if="followed" :key="followed" :job-id="followed" :label="label" quiet @ended="onEnded" @gone="onGone" />
    <template v-else>
      <p class="extraction__note">
        {{
          latest
            ? t("documents.page.lastStatus", { status: t(`jobs.status.${latest.status}`) })
            : t("documents.page.none")
        }}
      </p>
      <p v-if="unfollowed" class="extraction__note">{{ t("documents.page.following") }}</p>
      <div v-else-if="document.own" class="extraction__start">
        <p v-if="startFailure" class="field__error" role="alert">
          <AppIcon name="warning" /> <NoticeText :notice="startFailure" />
        </p>
        <!-- aria-disabled, not disabled: a disabled button drops the focus it holds -->
        <button
          type="button"
          class="btn primary"
          data-test="extraction-resume"
          :aria-disabled="starting || undefined"
          @click="resume"
        >
          {{ t("documents.page.resume") }}
        </button>
      </div>
      <p v-else class="extraction__note">{{ t("documents.page.notOwn") }}</p>
    </template>
    <!-- always in the page, so a screen reader hears each change of its text -->
    <p class="visually-hidden" role="status" data-test="extraction-status">{{ status }}</p>
  </section>
</template>

<style scoped>
.extraction__note {
  max-width: var(--reading-width);
  color: var(--text-muted);
  margin: 0 0 var(--space-2);
}

.extraction__start {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: var(--space-1);
}
</style>
