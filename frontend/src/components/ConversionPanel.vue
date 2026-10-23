<script setup lang="ts">
/**
 * The conversion of an entry's file into blocks (X0), on the entry's page: whether there is one,
 * how far it is while its job runs, what it found or why it failed - and the way to start it, to
 * start it again, and to its blocks. Only a PDF is converted so far, so another file is not asked
 * about; a file only the editors may read is said to be theirs, without a start. What happens
 * while the reader is on the page - started, done, failed - is announced in a region that is
 * there from the start; a state found on arrival is shown, not announced.
 */
import { computed, nextTick, onMounted, ref } from "vue";

import { ApiError, askConversion, getConversion, type Conversion } from "@/api";
import AppIcon from "@/components/AppIcon.vue";
import ConversionSummary from "@/components/ConversionSummary.vue";
import ErrorState from "@/components/ErrorState.vue";
import JobProgress from "@/components/JobProgress.vue";
import LoadingState from "@/components/LoadingState.vue";
import NoticeText from "@/components/NoticeText.vue";
import { conversionFailureText } from "@/conversionWords";
import { focusIsFree } from "@/focusRescue";
import { t } from "@/i18n/de";
import { sayAnew } from "@/liveRegion";
import { failureNotice, type Notice } from "@/notice";

/** The one type converted so far: the server refuses any other (422 not_pdf). */
const PDF = "application/pdf";

const props = defineProps<{ sourceId: string; mime: string }>();

const convertible = computed(() => props.mime === PDF);
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
// The latest answer counts: a reading asked for before a start is older than the start's answer
let generation = 0;

const failed = computed(() => conversion.value?.status === "failed");
const startable = computed(() => none.value || failed.value);

function refusedAs(error: unknown, status: number, code: string): boolean {
  return error instanceof ApiError && error.status === status && error.code === code;
}

/** What the page says of a conversion that came to its end while the reader was there. */
function outcome(state: Conversion): string {
  if (state.status === "done") return t("conversions.done", { pages: state.pages ?? 0 });
  if (state.status === "failed") return `${t("conversions.failed")} ${conversionFailureText(state.error_code)}`;
  return "";
}

function say(message: string): void {
  if (message) status.value = sayAnew(status.value, message);
}

/** The conversion as the server has it; `announce`: its job just ended, and how it ended is said. */
async function load({ announce = false } = {}): Promise<void> {
  const mine = ++generation;
  loading.value = true;
  failure.value = null;
  try {
    const found = await getConversion(props.sourceId);
    if (mine !== generation) return;
    conversion.value = found;
    none.value = false;
    hidden.value = false;
    if (announce) say(outcome(found));
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

onMounted(() => {
  if (convertible.value) void load();
});
</script>

<template>
  <section class="conversion" aria-labelledby="source-conversion">
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
          v-if="conversion.job_id"
          :key="conversion.job_id"
          :job-id="conversion.job_id"
          :label="t('conversions.jobLabel')"
          @ended="load({ announce: true })"
          @gone="load({ announce: true })"
        />
        <p v-else class="conversion__note">{{ t("jobs.status.queued") }}</p>
      </template>
      <ConversionSummary v-else-if="conversion.status === 'done'" :conversion="conversion" :source-id="sourceId" />
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
