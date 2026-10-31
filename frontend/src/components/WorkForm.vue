<script setup lang="ts">
/**
 * A document's work, set by an editor while the document has none and no IRI (plan M1 9.10, Paket 9d1 N5;
 * documentMeta.ts): one there is - the works of the documents the caller sees, there being no list of works - or a
 * new one, its title, its land and the short title its IRI takes. What is missing or a short title the IRI cannot
 * take is said at its field before anything is sent - the keyboard taken there from the button or from nothing,
 * else the problem said where the keyboard rests (Enter pressed in that field). Until the works are read only that is
 * shown, so no field goes from under the user. Set, the section is told (`saved`): the form goes with the work, the
 * section says it, and nothing more is sent meanwhile; the server's problem with a field stands at that field; a document named or frozen meanwhile is
 * said and read again (`changed`), another refusal said.
 */
import { nextTick, onMounted, ref, useId } from "vue";

import { listDocuments, type CurriculumDocument, type DocumentWork } from "@/api";
import AppIcon from "@/components/AppIcon.vue";
import NoticeText from "@/components/NoticeText.vue";
import { knownWorks, saveWork, shortTitleOk, workWords } from "@/documentMeta";
import { focusIsFree } from "@/focusRescue";
import { messages, t } from "@/i18n/de";
import { sayAnew } from "@/liveRegion";
import type { Notice } from "@/notice";
import { refusalText } from "@/refusals";
import { word } from "@/registerWords";

const props = defineProps<{ document: CurriculumDocument }>();
const emit = defineEmits<{ saved: []; changed: [] }>();

type Field = "work_id" | "title" | "region" | "short_title";

const REGIONS = Object.keys(messages.sources.countries);
const id = useId();
const works = ref<DocumentWork[]>([]);
const loading = ref(true);
const loadFailed = ref(false);
const mode = ref<"existing" | "new">("new");
const chosen = ref("");
const fresh = ref({ title: "", region: "", short_title: "" });
const busy = ref(false);
const status = ref("");
const submit = ref<HTMLElement | null>(null);
// a field's problem, said at the field; or one of the whole form, above the button
const fieldError = ref<{ field: Field; text: string } | null>(null);
const failure = ref<Notice | null>(null);

function regionWord(code: string): string {
  return word(messages.sources.countries, code);
}

/** The field's hint where it has one, and its error where it has one. */
function describedBy(field: Field, hint = false): string | undefined {
  const ids = [hint ? `${id}-${field}-hint` : "", fieldError.value?.field === field ? `${id}-${field}-error` : ""];
  return ids.filter(Boolean).join(" ") || undefined;
}

// each field's name, said with its problem where the keyboard stays elsewhere
const LABELS: Readonly<Record<Field, () => string>> = {
  work_id: () => t("documents.page.edition.workChosen"),
  title: () => t("documents.page.edition.workTitle"),
  region: () => t("documents.page.edition.workRegion"),
  short_title: () => t("documents.page.edition.workShortTitle"),
};

// A field's problem at the field. The keyboard goes there from the button or from nothing - the field reads the
// problem with its name -; resting elsewhere, or on the field already, it stays and the problem is said
async function faultAt(field: Field, text: string): Promise<void> {
  failure.value = null;
  fieldError.value = { field, text };
  await nextTick();
  if (document.activeElement === submit.value || focusIsFree()) {
    document.getElementById(`${id}-${field}`)?.focus();
    return;
  }
  status.value = sayAnew(status.value, t("documents.page.edition.fieldProblem", { field: LABELS[field](), problem: text }));
}

/** What is missing or wrong before anything is sent; null where the form may go. */
function unready(): [Field, string] | null {
  if (mode.value === "existing") return chosen.value ? null : ["work_id", t("documents.page.edition.workChoose")];
  if (!fresh.value.title.trim()) return ["title", t("documents.tree.problems.required")];
  if (!fresh.value.region) return ["region", t("documents.page.edition.workRegionChoose")];
  return shortTitleOk(fresh.value.short_title) ? null : ["short_title", t("documents.page.edition.workShortTitleBad")];
}

async function onSubmit(): Promise<void> {
  if (busy.value) return; // the button stays focusable while busy, so it can be pressed again
  const missing = unready();
  if (missing) return faultAt(...missing);
  fieldError.value = null;
  failure.value = null;
  busy.value = true;
  const work =
    mode.value === "existing"
      ? { work_id: chosen.value }
      : { title: fresh.value.title.trim(), region: fresh.value.region, short_title: fresh.value.short_title };
  const done = await saveWork(props.document.id, work);
  if (done.outcome === "saved") {
    emit("saved"); // busy until the form goes with the work: a second press would set it again
    return;
  }
  busy.value = false;
  if (done.outcome === "invalid") {
    const field = (["title", "region", "short_title"] as const).find((one) => one === done.field);
    if (field) await faultAt(field, done.problem);
    else failure.value = { text: done.problem, failed: true };
  } else if (done.outcome === "failed") {
    failure.value = done.problem;
  } else {
    failure.value = { text: refusalText(done.code) ?? t("documents.page.edition.workFailed"), failed: true };
    if (done.outcome === "closed") emit("changed");
  }
}

onMounted(async () => {
  try {
    works.value = knownWorks(await listDocuments());
    if (works.value.length) mode.value = "existing";
  } catch {
    loadFailed.value = true; // a new work can still be made
  } finally {
    loading.value = false;
  }
});
</script>

<template>
  <form class="work-form" novalidate @submit.prevent="onSubmit">
    <h3>{{ t("documents.page.edition.workHeading") }}</h3>
    <p class="field__hint">{{ t("documents.page.edition.workIntro") }}</p>
    <p v-if="loading" class="field__hint">{{ t("documents.page.edition.worksLoading") }}</p>
    <p v-else-if="loadFailed" class="field__hint">{{ t("documents.page.edition.worksFailed") }}</p>
    <p v-else-if="!works.length" class="field__hint">{{ t("documents.page.edition.workNone") }}</p>
    <template v-if="!loading">
      <fieldset v-if="works.length" class="work-form__choice">
        <legend>{{ t("documents.page.edition.workWhich") }}</legend>
        <label><input v-model="mode" type="radio" value="existing" /> {{ t("documents.page.edition.workExisting") }}</label>
        <label><input v-model="mode" type="radio" value="new" /> {{ t("documents.page.edition.workNew") }}</label>
      </fieldset>
      <div v-if="mode === 'existing'" class="field">
        <label :for="`${id}-work_id`">{{ t("documents.page.edition.workChosen") }}</label>
        <select
          :id="`${id}-work_id`"
          v-model="chosen"
          :aria-invalid="fieldError?.field === 'work_id' || undefined"
          :aria-describedby="describedBy('work_id')"
        >
          <option value="">{{ t("documents.page.edition.workChoosePlaceholder") }}</option>
          <option v-for="work in works" :key="work.id" :value="work.id">{{ workWords(work) }}</option>
        </select>
        <p v-if="fieldError?.field === 'work_id'" :id="`${id}-work_id-error`" class="field__error">
          <AppIcon name="warning" /> {{ fieldError.text }}
        </p>
      </div>
      <template v-else>
        <div class="field">
          <label :for="`${id}-title`">{{ t("documents.page.edition.workTitle") }}</label>
          <input
            :id="`${id}-title`"
            v-model="fresh.title"
            type="text"
            maxlength="1000"
            autocomplete="off"
            :aria-invalid="fieldError?.field === 'title' || undefined"
            :aria-describedby="describedBy('title')"
          />
          <p v-if="fieldError?.field === 'title'" :id="`${id}-title-error`" class="field__error">
            <AppIcon name="warning" /> {{ fieldError.text }}
          </p>
        </div>
        <div class="field">
          <label :for="`${id}-region`">{{ t("documents.page.edition.workRegion") }}</label>
          <select
            :id="`${id}-region`"
            v-model="fresh.region"
            :aria-invalid="fieldError?.field === 'region' || undefined"
            :aria-describedby="describedBy('region')"
          >
            <option value="">{{ t("documents.page.edition.workRegionPlaceholder") }}</option>
            <option v-for="code in REGIONS" :key="code" :value="code">{{ regionWord(code) }}</option>
          </select>
          <p v-if="fieldError?.field === 'region'" :id="`${id}-region-error`" class="field__error">
            <AppIcon name="warning" /> {{ fieldError.text }}
          </p>
        </div>
        <div class="field">
          <label :for="`${id}-short_title`">{{ t("documents.page.edition.workShortTitle") }}</label>
          <input
            :id="`${id}-short_title`"
            v-model="fresh.short_title"
            type="text"
            maxlength="200"
            autocomplete="off"
            spellcheck="false"
            :aria-invalid="fieldError?.field === 'short_title' || undefined"
            :aria-describedby="describedBy('short_title', true)"
          />
          <p v-if="fieldError?.field === 'short_title'" :id="`${id}-short_title-error`" class="field__error">
            <AppIcon name="warning" /> {{ fieldError.text }}
          </p>
          <p :id="`${id}-short_title-hint`" class="field__hint">{{ t("documents.page.edition.workShortTitleHint") }}</p>
        </div>
      </template>
      <p v-if="failure" class="field__error work-form__error" role="alert">
        <AppIcon name="warning" /> <NoticeText :notice="failure" />
      </p>
      <!-- aria-disabled, not disabled: a disabled button drops the focus it holds -->
      <button ref="submit" type="submit" class="btn secondary" :aria-disabled="busy || undefined">
        {{ t("documents.page.edition.workSave") }}
      </button>
    </template>
    <!-- always in the page, so a screen reader hears a field's problem said where the keyboard stayed -->
    <p class="visually-hidden" role="status">{{ status }}</p>
  </form>
</template>

<style scoped>
.work-form {
  display: grid;
  gap: var(--space-2);
  justify-items: start;
  max-width: var(--reading-width);
}

.work-form .field {
  justify-self: stretch;
}

.work-form h3,
.work-form p,
.work-form__choice {
  margin: 0;
}

.work-form__choice {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
}

.work-form__choice label {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  min-height: 24px;
}

/* The radio beside its name, as .extraction-start__box has it: the rule for every input would stretch it across
   the label and push the name to the next line. WCAG 2.5.8: 24px at least. */
.work-form__choice input[type="radio"] {
  flex: none;
  inline-size: 1.5rem;
  block-size: 1.5rem;
  min-height: 0;
  margin: 0;
  padding: 0;
}
</style>
