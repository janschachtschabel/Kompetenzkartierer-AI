<script setup lang="ts">
/**
 * An address into the register: the server enters it and starts the job that
 * fetches the file. Only a web address is sent; whether its host may be asked
 * at all is the server's to decide (no address inside its network). It reports
 * the entry and its job; following the job is the page's business.
 */
import { ref } from "vue";

import { ApiError, importSource, type ImportStarted } from "@/api";
import AppIcon from "@/components/AppIcon.vue";
import NoticeText from "@/components/NoticeText.vue";
import { t } from "@/i18n/de";
import { sayAnew } from "@/liveRegion";
import { failureNotice, type Notice } from "@/notice";

// `address` names the entry until its file arrives: an import's title is the file's name, unless one was given
const emit = defineEmits<{ imported: [started: ImportStarted, address: string] }>();

// The backend's limits on the address and the title (app/api/sources.py)
const MAX_URL_SIGNS = 2000;
const MAX_TITLE_SIGNS = 500;

const url = ref("");
const title = ref("");
const busy = ref(false);
const status = ref("");
const failure = ref<Notice | null>(null);
// a refusal of the address itself, said at its field; any other below the form
const urlRefused = ref(false);

function isWebAddress(candidate: string): boolean {
  try {
    return ["http:", "https:"].includes(new URL(candidate).protocol);
  } catch {
    return false; // no address at all
  }
}

/** The refusal to show; the same one again is read out again (liveRegion.ts). */
function refuse(notice: Notice, atUrl: boolean): void {
  failure.value = { ...notice, text: sayAnew(failure.value?.text ?? "", notice.text) };
  urlRefused.value = atUrl;
  status.value = "";
}

async function onSubmit(): Promise<void> {
  if (busy.value) return; // the button stays focusable while busy, so it can be pressed again
  const address = url.value.trim();
  if (!address) return refuse({ text: t("sources.import.errors.missing"), failed: true }, true);
  if (!isWebAddress(address)) return refuse({ text: t("sources.import.errors.scheme"), failed: true }, true);
  busy.value = true;
  failure.value = null;
  urlRefused.value = false;
  status.value = t("sources.import.busy");
  try {
    const started = await importSource(address, title.value);
    status.value = t("sources.import.started", { title: started.source.title || address });
    url.value = "";
    title.value = "";
    emit("imported", started, address);
  } catch (error) {
    refuse(failureNotice(error, t("sources.import.failed")), error instanceof ApiError && error.code === "url_invalid");
  } finally {
    busy.value = false;
  }
}
</script>

<template>
  <form class="source-form" novalidate @submit.prevent="onSubmit">
    <h3 class="source-form__heading">{{ t("sources.import.heading") }}</h3>
    <div class="field">
      <label for="import-url">{{ t("sources.import.urlLabel") }}</label>
      <input
        id="import-url"
        v-model="url"
        type="url"
        inputmode="url"
        :maxlength="MAX_URL_SIGNS"
        autocomplete="url"
        spellcheck="false"
        :aria-invalid="urlRefused || undefined"
        :aria-describedby="urlRefused ? 'import-url-hint import-error' : 'import-url-hint'"
      />
      <p id="import-url-hint" class="field__hint">{{ t("sources.import.urlHint") }}</p>
    </div>
    <div class="field">
      <label for="import-title">{{ t("sources.import.titleLabel") }}</label>
      <input
        id="import-title"
        v-model="title"
        type="text"
        :maxlength="MAX_TITLE_SIGNS"
        autocomplete="off"
        aria-describedby="import-title-hint"
      />
      <p id="import-title-hint" class="field__hint">{{ t("sources.import.titleHint") }}</p>
    </div>

    <p v-if="failure" id="import-error" class="field__error source-form__error" role="alert">
      <AppIcon name="warning" /> <NoticeText :notice="failure" />
    </p>
    <!-- aria-disabled, not disabled: a disabled button drops the focus it holds -->
    <button type="submit" class="btn primary" :aria-disabled="busy || undefined">
      {{ t("sources.import.submit") }}
    </button>
    <!-- Always in the page, so a screen reader hears each change of its text -->
    <p id="import-status" class="source-form__status" role="status">{{ status }}</p>
  </form>
</template>

