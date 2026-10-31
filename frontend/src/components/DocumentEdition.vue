<script setup lang="ts">
/**
 * A document's work and edition, on its page (plan M1 9.10, Paket 9d1 N5): its issuer, edition, work, IRI and
 * revision as they stand - what is not there said as such. Until it is frozen its owner and the editors change its
 * title, issuer and edition (DocumentMetaForm); an editor sets its work while it has none and no IRI (WorkForm). A
 * change saved below has the page read the document again (`changed`). A work set is said here, the work form going
 * with it; the keyboard, left on nothing as the form goes, is taken to the section's heading.
 */
import { computed, nextTick, ref, watch } from "vue";

import type { CurriculumDocument } from "@/api";
import DocumentMetaForm from "@/components/DocumentMetaForm.vue";
import WorkForm from "@/components/WorkForm.vue";
import { workWords } from "@/documentMeta";
import { focusIsFree } from "@/focusRescue";
import { t } from "@/i18n/de";
import { sayAnew } from "@/liveRegion";
import { isEditor } from "@/session";

const props = defineProps<{ document: CurriculumDocument }>();
const emit = defineEmits<{ changed: [] }>();

const open = computed(() => props.document.frozen_at === null);
const mayChange = computed(() => open.value && (props.document.own || isEditor()));
const maySetWork = computed(
  () => open.value && isEditor() && props.document.work === null && props.document.iri === null,
);
const heading = ref<HTMLElement | null>(null);
const status = ref("");

function workSaved(): void {
  status.value = sayAnew(status.value, t("documents.page.edition.workSaved"));
  emit("changed");
}

watch(maySetWork, async (now, was) => {
  if (now || !was) return;
  await nextTick();
  if (focusIsFree()) heading.value?.focus();
});
</script>

<template>
  <section class="edition" aria-labelledby="document-edition">
    <!-- tabindex -1: where the keyboard goes once the work form went with the work set -->
    <h2 id="document-edition" ref="heading" tabindex="-1">{{ t("documents.page.edition.heading") }}</h2>
    <dl class="facts">
      <dt>{{ t("documents.page.edition.issuer") }}</dt>
      <dd>{{ document.issuer || t("documents.page.edition.none") }}</dd>
      <dt>{{ t("documents.page.edition.edition") }}</dt>
      <dd>{{ document.edition || t("documents.page.edition.none") }}</dd>
      <dt>{{ t("documents.page.edition.workHeading") }}</dt>
      <dd>{{ document.work ? workWords(document.work) : t("documents.page.edition.none") }}</dd>
      <dt>{{ t("documents.page.edition.iri") }}</dt>
      <dd>{{ document.iri || t("documents.page.edition.noIri") }}</dd>
      <dt>{{ t("documents.page.edition.revision") }}</dt>
      <dd>{{ document.revision }}</dd>
    </dl>
    <DocumentMetaForm v-if="mayChange" :document="document" @changed="emit('changed')" />
    <WorkForm v-if="maySetWork" :document="document" @saved="workSaved" @changed="emit('changed')" />
    <!-- always in the section, so a screen reader hears what a form said before it went -->
    <p class="visually-hidden edition__status" role="status">{{ status }}</p>
  </section>
</template>

<style scoped>
.edition {
  display: grid;
  gap: var(--space-3);
  align-content: start;
}

.edition h2,
.edition .facts {
  margin: 0;
}
</style>
