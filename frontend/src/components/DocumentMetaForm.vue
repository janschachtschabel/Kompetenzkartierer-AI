<script setup lang="ts">
/**
 * A document's title, issuer and edition (plan M1 9.10, Paket 9d1 N5; documentMeta.ts), by its owner or an editor:
 * only what changed is sent, an emptied field as none. Once the document has its IRI the issuer and the edition it
 * is made of stand as they are, the title still to change. Saved, it says so and the page reads the document again
 * (`changed`); a field's problem stands at the field, the keyboard taken there and the entry kept; a document closed
 * to the change meanwhile is said and read again, another refusal said. Read again, each field the user left as it
 * was takes the value read - the extraction may have filled it meanwhile -, an entry not yet saved stays; saved, the
 * fields sent take the values the server stored.
 */
import { computed, nextTick, ref, useId, watch } from "vue";

import type { CurriculumDocument } from "@/api";
import AppIcon from "@/components/AppIcon.vue";
import NoticeText from "@/components/NoticeText.vue";
import { metaChanges, saveMeta, type MetaDraft } from "@/documentMeta";
import { t } from "@/i18n/de";
import { sayAnew } from "@/liveRegion";
import type { Notice } from "@/notice";
import { refusalText } from "@/refusals";

const props = defineProps<{ document: CurriculumDocument }>();
const emit = defineEmits<{ changed: [] }>();

type Field = keyof MetaDraft;
const FIELDS: readonly Field[] = ["title", "issuer", "edition"];

const id = useId();
const draftOf = (document: CurriculumDocument): MetaDraft => ({
  title: document.title ?? "",
  issuer: document.issuer ?? "",
  edition: document.edition ?? "",
});
// what the draft began from: the document as read, or as a save gave it back
const base = ref(props.document);
const draft = ref(draftOf(props.document));
const busy = ref(false);
const status = ref("");
// a field's problem, said at the field; or one of the whole form, above the button
const fieldError = ref<{ field: Field; text: string } | null>(null);
const failure = ref<Notice | null>(null);

const named = computed(() => props.document.iri !== null);
// each field as the form shows it; with an IRI the issuer and the edition only to read
const inputs = computed(() => [
  {
    key: "title" as const,
    label: t("documents.page.edition.title"),
    hint: t("documents.page.edition.titleHint"),
    max: 1000,
    autocomplete: "off",
    locked: false,
  },
  {
    key: "issuer" as const,
    label: t("documents.page.edition.issuer"),
    hint: named.value ? t("documents.page.edition.named") : t("documents.page.edition.issuerHint"),
    max: 500,
    autocomplete: "organization",
    locked: named.value,
  },
  {
    key: "edition" as const,
    label: t("documents.page.edition.edition"),
    hint: named.value ? t("documents.page.edition.named") : t("documents.page.edition.editionHint"),
    max: 200,
    autocomplete: "off",
    locked: named.value,
  },
]);

// The document read anew: a field left as it was, or one just saved, takes the value read; an entry stays
function rebase(now: CurriculumDocument, saved: readonly string[] = []): void {
  const was = draftOf(base.value);
  const next = draftOf(now);
  for (const key of FIELDS) {
    if (saved.includes(key) || draft.value[key].trim() === was[key].trim()) draft.value[key] = next[key];
  }
  base.value = now;
}

watch(
  () => props.document,
  (now) => rebase(now),
);

/** The field's hint, and its error where it has one. */
function describedBy(field: Field): string {
  const hint = `${id}-${field}-hint`;
  return fieldError.value?.field === field ? `${hint} ${id}-${field}-error` : hint;
}

// a field's problem at the field, the keyboard taken there: it reads the problem with the field's name
async function faultAt(field: Field, text: string): Promise<void> {
  fieldError.value = { field, text };
  await nextTick();
  document.getElementById(`${id}-${field}`)?.focus();
}

function refuse(text: string): void {
  failure.value = { text: sayAnew(failure.value?.text ?? "", text), failed: true };
}

async function onSubmit(): Promise<void> {
  if (busy.value) return; // the button stays focusable while busy, so it can be pressed again
  const changes = metaChanges(base.value, draft.value);
  failure.value = null;
  fieldError.value = null;
  if (!Object.keys(changes).length) {
    status.value = sayAnew(status.value, t("documents.page.edition.unchanged"));
    return;
  }
  status.value = "";
  busy.value = true;
  const done = await saveMeta(props.document.id, changes);
  busy.value = false;
  if (done.outcome === "saved") {
    rebase(done.document, Object.keys(changes));
    status.value = sayAnew(status.value, t("documents.page.edition.saved"));
    emit("changed");
  } else if (done.outcome === "invalid") {
    const field = FIELDS.find((one) => one === done.field);
    if (field) await faultAt(field, done.problem);
    else refuse(done.problem);
  } else if (done.outcome === "failed") {
    failure.value = done.problem;
  } else {
    refuse(refusalText(done.code) ?? t("documents.page.edition.saveFailed"));
    if (done.outcome === "closed") emit("changed");
  }
}
</script>

<template>
  <form class="meta-form" novalidate @submit.prevent="onSubmit">
    <h3>{{ t("documents.page.edition.metaHeading") }}</h3>
    <div v-for="input in inputs" :key="input.key" class="field">
      <label :for="`${id}-${input.key}`">{{ input.label }}</label>
      <input
        :id="`${id}-${input.key}`"
        v-model="draft[input.key]"
        type="text"
        :maxlength="input.max"
        :autocomplete="input.autocomplete"
        :readonly="input.locked"
        :aria-invalid="fieldError?.field === input.key || undefined"
        :aria-describedby="describedBy(input.key)"
      />
      <p v-if="fieldError?.field === input.key" :id="`${id}-${input.key}-error`" class="field__error">
        <AppIcon name="warning" /> {{ fieldError.text }}
      </p>
      <p :id="`${id}-${input.key}-hint`" class="field__hint">{{ input.hint }}</p>
    </div>
    <p v-if="failure" class="field__error meta-form__error" role="alert">
      <AppIcon name="warning" /> <NoticeText :notice="failure" />
    </p>
    <!-- aria-disabled, not disabled: a disabled button drops the focus it holds -->
    <button type="submit" class="btn primary" :aria-disabled="busy || undefined">
      {{ t("documents.page.edition.save") }}
    </button>
    <!-- always in the page, so a screen reader hears each change of its text -->
    <p class="meta-form__status" role="status">{{ status }}</p>
  </form>
</template>

<style scoped>
.meta-form {
  display: grid;
  gap: var(--space-2);
  justify-items: start;
  max-width: var(--reading-width);
}

.meta-form .field {
  justify-self: stretch;
}

.meta-form h3,
.meta-form__error,
.meta-form__status {
  margin: 0;
}

/* Empty, it takes no room - as a cell of the grid its gap would stand twice - but stays in the page. */
.meta-form__status:empty {
  position: absolute;
}
</style>
