<script setup lang="ts">
/**
 * A document's work, set by an editor while the document has none and no IRI (plan M1 9.10, Paket 9d1 N5;
 * documentMeta.ts): one there is - the works of the documents the caller sees, there being no list of works - or a
 * new one, its title, its land and the short title its IRI takes. What is missing or a short title the IRI cannot
 * take is said at its field before anything is sent. Set, it says so and the page reads the document again
 * (`changed`); the server's problem with a field stands at that field; a document named or frozen meanwhile is said
 * and read again, another refusal said.
 */
import { computed, onMounted, ref, useId } from "vue";

import { listDocuments, type CurriculumDocument, type DocumentWork } from "@/api";
import AppIcon from "@/components/AppIcon.vue";
import NoticeText from "@/components/NoticeText.vue";
import { knownWorks, saveWork, shortTitleOk, workWords } from "@/documentMeta";
import { messages, t } from "@/i18n/de";
import { sayAnew } from "@/liveRegion";
import type { Notice } from "@/notice";
import { refusalText } from "@/refusals";
import { word } from "@/registerWords";

const props = defineProps<{ document: CurriculumDocument }>();
const emit = defineEmits<{ changed: [] }>();

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
// a field's problem, said at the field and above the button; or one of the whole form
const fieldError = ref<{ field: Field; text: string } | null>(null);
const failure = ref<Notice | null>(null);

const problem = computed<Notice | null>(() =>
  fieldError.value ? { text: fieldError.value.text, failed: true } : failure.value,
);

function regionWord(code: string): string {
  return word(messages.sources.countries, code);
}

/** The field's hint where it has one, and the error where it is this field's. */
function describedBy(field: Field, hint = false): string | undefined {
  const ids = [hint ? `${id}-${field}-hint` : "", fieldError.value?.field === field ? `${id}-error` : ""];
  return ids.filter(Boolean).join(" ") || undefined;
}

function fault(field: Field, text: string): void {
  failure.value = null;
  fieldError.value = { field, text };
  status.value = "";
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
  if (missing) return fault(...missing);
  fieldError.value = null;
  failure.value = null;
  busy.value = true;
  const work =
    mode.value === "existing"
      ? { work_id: chosen.value }
      : { title: fresh.value.title.trim(), region: fresh.value.region, short_title: fresh.value.short_title };
  const done = await saveWork(props.document.id, work);
  busy.value = false;
  if (done.outcome === "saved") {
    status.value = sayAnew(status.value, t("documents.page.edition.workSaved"));
    emit("changed");
  } else if (done.outcome === "invalid") {
    const field = (["title", "region", "short_title"] as const).find((one) => one === done.field);
    if (field) fault(field, done.problem);
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
    <fieldset v-if="works.length" class="work-form__choice">
      <legend>{{ t("documents.page.edition.workWhich") }}</legend>
      <label><input v-model="mode" type="radio" value="existing" /> {{ t("documents.page.edition.workExisting") }}</label>
      <label><input v-model="mode" type="radio" value="new" /> {{ t("documents.page.edition.workNew") }}</label>
    </fieldset>
    <div v-if="mode === 'existing'" class="field">
      <label :for="`${id}-work`">{{ t("documents.page.edition.workChosen") }}</label>
      <select
        :id="`${id}-work`"
        v-model="chosen"
        :aria-invalid="fieldError?.field === 'work_id' || undefined"
        :aria-describedby="describedBy('work_id')"
      >
        <option value="">{{ t("documents.page.edition.workChoosePlaceholder") }}</option>
        <option v-for="work in works" :key="work.id" :value="work.id">{{ workWords(work) }}</option>
      </select>
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
        <p :id="`${id}-short_title-hint`" class="field__hint">{{ t("documents.page.edition.workShortTitleHint") }}</p>
      </div>
    </template>
    <p v-if="problem" :id="`${id}-error`" class="field__error work-form__error" role="alert">
      <AppIcon name="warning" /> <NoticeText :notice="problem" />
    </p>
    <!-- aria-disabled, not disabled: a disabled button drops the focus it holds -->
    <button type="submit" class="btn secondary" :aria-disabled="busy || undefined">
      {{ t("documents.page.edition.workSave") }}
    </button>
    <!-- always in the page, so a screen reader hears each change of its text -->
    <p class="work-form__status" role="status">{{ status }}</p>
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

/* Empty, it takes no room - as a cell of the grid its gap would stand twice - but stays in the page. */
.work-form__status:empty {
  position: absolute;
}
</style>
