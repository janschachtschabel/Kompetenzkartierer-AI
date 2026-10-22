<script setup lang="ts">
/**
 * The check of the seed, for an admin: every candidate's address asked once
 * (backend source.check). It asks the servers of others, so the page asks
 * first; a check that waits or runs already is followed rather than started
 * again (409 check_running). The job goes to the page, which follows it.
 */
import { ref } from "vue";

import { ApiError, startCheck } from "@/api";
import AppIcon from "@/components/AppIcon.vue";
import ConfirmDialog from "@/components/ConfirmDialog.vue";
import NoticeText from "@/components/NoticeText.vue";
import { t } from "@/i18n/de";
import { sayAnew } from "@/liveRegion";
import { failureNotice, type Notice } from "@/notice";

const emit = defineEmits<{ started: [jobId: string] }>();

const asking = ref(false);
const busy = ref(false);
const status = ref("");
const failure = ref<Notice | null>(null);

function ask(): void {
  if (!busy.value) asking.value = true;
}

async function start(): Promise<void> {
  asking.value = false;
  busy.value = true;
  failure.value = null;
  try {
    const started = await startCheck();
    status.value = sayAnew(status.value, t("sources.check.started"));
    emit("started", started.job_id);
  } catch (error) {
    const running = runningCheck(error);
    if (running) {
      status.value = sayAnew(status.value, t("sources.check.running"));
      emit("started", running);
    } else {
      status.value = "";
      failure.value = failureNotice(error, t("sources.check.failed"));
    }
  } finally {
    busy.value = false;
  }
}

/** The job of the check that waits or runs already, as the server names it in its refusal. */
function runningCheck(error: unknown): string | null {
  if (!(error instanceof ApiError) || error.status !== 409 || error.code !== "check_running") return null;
  const id = error.details.job_id;
  return typeof id === "string" ? id : null;
}
</script>

<template>
  <section class="check card" aria-labelledby="sources-check">
    <h2 id="sources-check" class="check__heading">{{ t("sources.check.heading") }}</h2>
    <p class="check__intro">{{ t("sources.check.intro") }}</p>
    <p v-if="failure" class="field__error" role="alert">
      <AppIcon name="warning" /> <NoticeText :notice="failure" />
    </p>
    <!-- aria-disabled, not disabled: a disabled button drops the focus it holds -->
    <button
      type="button"
      class="btn primary"
      data-test="check-start"
      :aria-disabled="busy || undefined"
      @click="ask"
    >
      {{ t("sources.check.start") }}
    </button>
    <!-- Always in the page, so a screen reader hears each change of its text -->
    <p class="check__status" role="status" data-test="check-status">{{ status }}</p>
    <ConfirmDialog
      v-if="asking"
      :title="t('sources.check.confirmTitle')"
      :message="t('sources.check.confirmMessage')"
      :confirm-label="t('sources.check.confirm')"
      :danger="false"
      @confirm="start"
      @cancel="asking = false"
    />
  </section>
</template>

<style scoped>
.check {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: var(--space-1);
  margin: 0;
}

.check__heading {
  margin: 0;
}

.check__intro {
  max-width: var(--reading-width);
  margin: 0;
  color: var(--text-muted);
}

.check__status {
  margin: 0;
  font-size: var(--step--1);
}
</style>
