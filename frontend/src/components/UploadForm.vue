<script setup lang="ts">
/**
 * A file into the register: chosen, titled where the account wishes, held
 * against the upload limit before its megabytes travel, and sent. It reports
 * the entry it made; reading the register again is the page's business.
 */
import { computed, ref } from "vue";

import { ApiError, uploadSource, type SourceOut } from "@/api";
import AppIcon from "@/components/AppIcon.vue";
import NoticeText from "@/components/NoticeText.vue";
import { t } from "@/i18n/de";
import { sayAnew } from "@/liveRegion";
import { failureNotice, type Notice } from "@/notice";

const props = defineProps<{
  /** MAX_UPLOAD_MB, where the service's facts loaded; without it the server alone decides. */
  maxUploadMb?: number;
}>();
const emit = defineEmits<{ uploaded: [source: SourceOut] }>();

// A hint to the file picker: the server decides by the bytes (backend app/sources/filetype.py)
const ACCEPT = ".pdf,.docx,.rtf,.html,.htm,.md,.markdown,.txt,.ttl";
const MIB = 2 ** 20;
// The backend's MAX_TITLE_SIGNS
const MAX_TITLE_SIGNS = 500;

type Field = "file" | "title";
// The refusals about the title; the others about the file are told by their status
const TITLE_CODES: ReadonlySet<unknown> = new Set(["title_invalid", "title_too_long"]);

const fileInput = ref<HTMLInputElement | null>(null);
const file = ref<File | null>(null);
const title = ref("");
const busy = ref(false);
const status = ref("");
const failure = ref<Notice | null>(null);
const failedField = ref<Field | null>(null);

const fileHint = computed(() =>
  props.maxUploadMb
    ? t("sources.upload.fileHint", { limit: props.maxUploadMb })
    : t("sources.upload.fileHintNoLimit"),
);

/** The help, and the error where it is this field's. */
function describedBy(field: Field): string {
  return failedField.value === field ? `upload-${field}-hint upload-error` : `upload-${field}-hint`;
}

function onChosen(event: Event): void {
  file.value = (event.target as HTMLInputElement).files?.[0] ?? null;
}

/** The refusal to show; the same one again is read out again (liveRegion.ts). */
function refuse(notice: Notice, field: Field | null): void {
  failure.value = { ...notice, text: sayAnew(failure.value?.text ?? "", notice.text) };
  failedField.value = field;
  status.value = "";
}

function tooLarge(): string {
  return t("sources.upload.errors.tooLarge", { limit: props.maxUploadMb ?? 0 });
}

function fieldOf(error: unknown): Field | null {
  if (!(error instanceof ApiError)) return null;
  if (TITLE_CODES.has(error.code)) return "title";
  return error.status === 413 || error.status === 415 || error.code === "file_missing" ? "file" : null;
}

function uploadFailure(error: unknown): Notice {
  const text = t("sources.upload.failed");
  // a body cut at the server's limit is a file too large, whatever its code says: the limit is known here
  if (error instanceof ApiError && error.status === 413 && error.code !== "archive_too_large" && props.maxUploadMb) {
    return { text, explanation: tooLarge(), failed: true };
  }
  return failureNotice(error, text);
}

async function onSubmit(): Promise<void> {
  if (busy.value) return; // the button stays focusable while busy, so it can be pressed again
  const chosen = file.value;
  if (!chosen) return refuse({ text: t("sources.upload.errors.missing"), failed: true }, "file");
  if (props.maxUploadMb && chosen.size > props.maxUploadMb * MIB) {
    return refuse({ text: tooLarge(), failed: true }, "file");
  }
  busy.value = true;
  failure.value = null;
  failedField.value = null;
  status.value = t("sources.upload.busy");
  try {
    const source = await uploadSource(chosen, title.value);
    status.value = t("sources.upload.done", { title: source.title });
    file.value = null;
    title.value = "";
    if (fileInput.value) fileInput.value.value = "";
    emit("uploaded", source);
  } catch (error) {
    refuse(uploadFailure(error), fieldOf(error));
  } finally {
    busy.value = false;
  }
}
</script>

<template>
  <form class="source-form" novalidate @submit.prevent="onSubmit">
    <h3 class="source-form__heading">{{ t("sources.upload.heading") }}</h3>
    <div class="field">
      <label for="upload-file">{{ t("sources.upload.fileLabel") }}</label>
      <input
        id="upload-file"
        ref="fileInput"
        type="file"
        :accept="ACCEPT"
        :aria-invalid="failedField === 'file' || undefined"
        :aria-describedby="describedBy('file')"
        @change="onChosen"
      />
      <p id="upload-file-hint" class="field__hint">{{ fileHint }}</p>
    </div>
    <div class="field">
      <label for="upload-title">{{ t("sources.upload.titleLabel") }}</label>
      <input
        id="upload-title"
        v-model="title"
        type="text"
        :maxlength="MAX_TITLE_SIGNS"
        autocomplete="off"
        :aria-invalid="failedField === 'title' || undefined"
        :aria-describedby="describedBy('title')"
      />
      <p id="upload-title-hint" class="field__hint">{{ t("sources.upload.titleHint") }}</p>
    </div>

    <p v-if="failure" id="upload-error" class="field__error source-form__error" role="alert">
      <AppIcon name="warning" /> <NoticeText :notice="failure" />
    </p>
    <!-- aria-disabled, not disabled: a disabled button drops the focus it holds -->
    <button type="submit" class="btn primary" :aria-disabled="busy || undefined">
      {{ t("sources.upload.submit") }}
    </button>
    <!-- Always in the page, so a screen reader hears each change of its text -->
    <p id="upload-status" class="source-form__status" role="status">{{ status }}</p>
  </form>
</template>

