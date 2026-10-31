<script setup lang="ts">
/**
 * A document's title, issuer and edition (plan M1 9.10, Paket 9d1 N5; documentMeta.ts), by its owner or an editor:
 * only what changed is sent, an emptied field as none. Once the document has its IRI the issuer and the edition it
 * is made of stand as they are, the title still to change. Saved, it says so and the page reads the document again
 * (`changed`); a field's problem stands at the field and above the button, the entry kept; a document closed to the
 * change meanwhile is said and read again, another refusal said. An entry not yet saved stays where the document is
 * read again for another reason; one saved takes the values read.
 */
import { computed, ref, useId, watch } from "vue";

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
const failure = ref<Notice | null>(null);
const failedField = ref<Field | null>(null);

const named = computed(() => props.document.iri !== null);
const dirty = computed(() => Object.keys(metaChanges(base.value, draft.value)).length > 0);

watch(
  () => props.document,
  (now) => {
    if (dirty.value) return;
    base.value = now;
    draft.value = draftOf(now);
  },
);

/** The field's hint, and the error where it is this field's. */
function describedBy(field: Field): string {
  const hint = `${id}-${field}-hint`;
  return failedField.value === field ? `${hint} ${id}-error` : hint;
}

function refuse(text: string, field: Field | null = null): void {
  failure.value = { text: sayAnew(failure.value?.text ?? "", text), failed: true };
  failedField.value = field;
  status.value = "";
}

async function onSubmit(): Promise<void> {
  if (busy.value) return; // the button stays focusable while busy, so it can be pressed again
  const changes = metaChanges(base.value, draft.value);
  failure.value = null;
  failedField.value = null;
  if (!Object.keys(changes).length) {
    status.value = sayAnew(status.value, t("documents.page.edition.unchanged"));
    return;
  }
  busy.value = true;
  const done = await saveMeta(props.document.id, changes);
  busy.value = false;
  if (done.outcome === "saved") {
    base.value = done.document;
    status.value = sayAnew(status.value, t("documents.page.edition.saved"));
    emit("changed");
  } else if (done.outcome === "invalid") {
    const field = (["title", "issuer", "edition"] as const).find((one) => one === done.field) ?? null;
    refuse(done.problem, field);
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
    <div class="field">
      <label :for="`${id}-title`">{{ t("documents.page.edition.title") }}</label>
      <input
        :id="`${id}-title`"
        v-model="draft.title"
        type="text"
        maxlength="1000"
        autocomplete="off"
        :aria-invalid="failedField === 'title' || undefined"
        :aria-describedby="describedBy('title')"
      />
      <p :id="`${id}-title-hint`" class="field__hint">{{ t("documents.page.edition.titleHint") }}</p>
    </div>
    <div class="field">
      <label :for="`${id}-issuer`">{{ t("documents.page.edition.issuer") }}</label>
      <input
        :id="`${id}-issuer`"
        v-model="draft.issuer"
        type="text"
        maxlength="500"
        autocomplete="organization"
        :readonly="named"
        :aria-invalid="failedField === 'issuer' || undefined"
        :aria-describedby="describedBy('issuer')"
      />
      <p :id="`${id}-issuer-hint`" class="field__hint">
        {{ named ? t("documents.page.edition.named") : t("documents.page.edition.issuerHint") }}
      </p>
    </div>
    <div class="field">
      <label :for="`${id}-edition`">{{ t("documents.page.edition.edition") }}</label>
      <input
        :id="`${id}-edition`"
        v-model="draft.edition"
        type="text"
        maxlength="200"
        autocomplete="off"
        :readonly="named"
        :aria-invalid="failedField === 'edition' || undefined"
        :aria-describedby="describedBy('edition')"
      />
      <p :id="`${id}-edition-hint`" class="field__hint">
        {{ named ? t("documents.page.edition.named") : t("documents.page.edition.editionHint") }}
      </p>
    </div>
    <p v-if="failure" :id="`${id}-error`" class="field__error meta-form__error" role="alert">
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
