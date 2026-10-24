<script setup lang="ts">
/**
 * A document's work packages (plan M1 7b, F14): each with its section, its pages and how far the
 * extraction has come with it - its statements read and written, open, a frame part read typed,
 * or not read at all. Read again whenever `refresh` changes (the page bumps it as the extraction
 * moves on); the list shown stays meanwhile, and stays where a later reading fails, said beside it.
 * The latest reading counts: an answer overtaken by a later question is dropped. A retry the reader
 * asks for shows its waiting where nothing is shown yet, says a failure again even in the same
 * words, and takes the keyboard to the section's heading once its button went with the notice.
 */
import { computed, onMounted, ref, watch } from "vue";

import { getUnits, type Unit } from "@/api";
import EmptyState from "@/components/EmptyState.vue";
import ErrorState from "@/components/ErrorState.vue";
import LoadingState from "@/components/LoadingState.vue";
import PartialState from "@/components/PartialState.vue";
import { focusIsFree } from "@/focusRescue";
import { t } from "@/i18n/de";
import { sayAnew } from "@/liveRegion";
import { failureNotice, type Notice } from "@/notice";

const props = defineProps<{ documentId: string; refresh: number }>();

const units = ref<Unit[] | null>(null);
const failure = ref<Notice | null>(null);
const heading = ref<HTMLElement | null>(null);
let generation = 0;
// where the reader's retry began, until the list it asked for is shown; undefined: none asked
let retriedFrom: Element | null | undefined;

const read = computed(() => (units.value ?? []).filter((unit) => unit.state === "done" || unit.state === "open"));
const done = computed(() => read.value.filter((unit) => unit.state === "done").length);

async function load(): Promise<void> {
  const mine = ++generation;
  try {
    const found = await getUnits(props.documentId);
    if (mine !== generation) return;
    units.value = found;
    failure.value = null;
  } catch (error) {
    if (mine !== generation) return;
    failure.value = failureNotice(error, t("documents.units.loadFailed"));
  }
}

/** A reading the reader asked for; a reading as the extraction moves on stays without either. */
async function retry(): Promise<void> {
  retriedFrom = document.activeElement;
  const before = failure.value;
  if (units.value === null) failure.value = null; // the waiting shows, and the alert comes again
  await load();
  if (failure.value && before && units.value !== null) {
    failure.value = { ...failure.value, text: sayAnew(before.text, failure.value.text) };
  }
  if (failure.value) retriedFrom = undefined;
}

// after the render, before the focus rescue takes a focus the render dropped to the main region;
// only where the focus still rests where the retry began, or nowhere
watch(
  units,
  () => {
    const from = retriedFrom;
    retriedFrom = undefined;
    if (from !== undefined && (document.activeElement === from || focusIsFree())) heading.value?.focus();
  },
  { flush: "post" },
);

function section(unit: Unit): string {
  if (unit.path.length) return unit.path.join(" / ");
  // X2 names what stands before the first heading E0; a document without headings is E1 alone
  return unit.key === "E0" ? t("documents.units.titlePages") : t("documents.units.wholeDocument");
}

function pages(unit: Unit): string {
  const [first, last] = unit.pages;
  return first === last ? t("documents.units.page", { first }) : t("documents.units.pages", { first, last });
}

function state(unit: Unit): string {
  return unit.state === "done"
    ? t("documents.units.states.done", { statements: unit.statements ?? 0 })
    : t(`documents.units.states.${unit.state}`);
}

onMounted(load);
watch(() => props.refresh, load);
</script>

<template>
  <section aria-labelledby="document-units">
    <!-- tabindex -1: where the keyboard goes once a retry's button went with its notice -->
    <h2 id="document-units" ref="heading" tabindex="-1">{{ t("documents.units.heading") }}</h2>
    <template v-if="units === null">
      <ErrorState
        v-if="failure"
        :message="failure.text"
        :reason="failure.reason"
        :explanation="failure.explanation"
        @retry="retry()"
      />
      <LoadingState v-else :label="t('documents.units.loading')" />
    </template>
    <EmptyState
      v-else-if="!units.length"
      :level="3"
      :title="t('documents.units.noneTitle')"
      :body="t('documents.units.noneBody')"
    />
    <template v-else>
      <p v-if="read.length" class="units__note" data-test="units-summary">
        {{ t("documents.units.summary", { done, total: read.length }) }}
      </p>
      <!-- scrolled on its own where wider than a phone, by the keyboard too; a name of its own -->
      <div class="units" tabindex="0" role="region" :aria-label="t('documents.units.table')">
        <table>
          <thead>
            <tr>
              <th scope="col">{{ t("documents.units.columns.key") }}</th>
              <th scope="col">{{ t("documents.units.columns.path") }}</th>
              <th scope="col">{{ t("documents.units.columns.pages") }}</th>
              <th scope="col">{{ t("documents.units.columns.state") }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="unit in units" :key="unit.key">
              <td>{{ unit.key }}</td>
              <td><bdi class="units__path">{{ section(unit) }}</bdi></td>
              <td>{{ pages(unit) }}</td>
              <td>{{ state(unit) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>
    <!-- in the page from the start, so a failure of a later reading is heard -->
    <PartialState :notice="units !== null ? failure : null" retry @retry="retry()" />
  </section>
</template>

<style scoped>
.units {
  overflow-x: auto;
}

.units table {
  border-collapse: collapse;
  min-width: 32rem;
}

.units th,
.units td {
  padding: var(--space-0) var(--space-2) var(--space-0) 0;
  text-align: start;
  vertical-align: top;
}

.units__path {
  overflow-wrap: anywhere;
}

.units__note {
  max-width: var(--reading-width);
  color: var(--text-muted);
  margin: 0 0 var(--space-2);
}
</style>
