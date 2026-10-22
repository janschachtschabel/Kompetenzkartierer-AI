<script setup lang="ts">
/**
 * An address into the register: the server enters it and starts the job that
 * fetches the file. Only a web address is sent; whether its host may be asked
 * at all is the server's to decide (no address inside its network). It reports
 * the entry and its job; following the job is the page's business.
 */
import { ref } from "vue";

import { ApiError, importSource, MAX_TITLE_SIGNS, MAX_URL_SIGNS, type ImportStarted } from "@/api";
import { isolate } from "@/bidi";
import AppIcon from "@/components/AppIcon.vue";
import NoticeText from "@/components/NoticeText.vue";
import { t } from "@/i18n/de";
import { sayAnew } from "@/liveRegion";
import { failureNotice, type Notice } from "@/notice";

// `address` names the entry until its file arrives: an import's title is the file's name, unless one was given
const emit = defineEmits<{ imported: [started: ImportStarted, address: string] }>();

const url = ref("");
const title = ref("");
const busy = ref(false);
const status = ref("");
const failure = ref<Notice | null>(null);
// a refusal of the address itself, said at its field; any other below the form
const urlRefused = ref(false);

/**
 * Why the server would not fetch `candidate`, as a catalogue key; null for a web
 * address it takes up. The server checks again (url_invalid): this spares the
 * request, and a password never leaves the page.
 */
function addressFault(candidate: string): string | null {
  if (/\s/.test(candidate)) return "sources.import.errors.spaces";
  let parsed: URL;
  try {
    parsed = new URL(candidate);
  } catch {
    return "sources.import.errors.scheme"; // no address at all
  }
  if (!["http:", "https:"].includes(parsed.protocol)) return "sources.import.errors.scheme";
  return parsed.username || parsed.password ? "sources.import.errors.credentials" : null;
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
  const fault = addressFault(address);
  if (fault) return refuse({ text: t(fault), failed: true }, true);
  busy.value = true;
  failure.value = null;
  urlRefused.value = false;
  status.value = t("sources.import.busy");
  try {
    const started = await importSource(address, title.value);
    status.value = t("sources.import.started", { title: isolate(started.source.title || address) });
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

