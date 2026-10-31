<script setup lang="ts">
/**
 * A document's work and edition, on its page (plan M1 9.10, Paket 9d1 N5): its issuer, edition, work, IRI and
 * revision as they stand - what is not there said as such. Until it is frozen its owner and the editors change its
 * title, issuer and edition (DocumentMetaForm); an editor sets its work while it has none and no IRI (WorkForm). A
 * change saved below has the page read the document again (`changed`).
 */
import { computed } from "vue";

import type { CurriculumDocument } from "@/api";
import DocumentMetaForm from "@/components/DocumentMetaForm.vue";
import WorkForm from "@/components/WorkForm.vue";
import { workWords } from "@/documentMeta";
import { t } from "@/i18n/de";
import { isEditor } from "@/session";

const props = defineProps<{ document: CurriculumDocument }>();
const emit = defineEmits<{ changed: [] }>();

const open = computed(() => props.document.frozen_at === null);
const mayChange = computed(() => open.value && (props.document.own || isEditor()));
const maySetWork = computed(
  () => open.value && isEditor() && props.document.work === null && props.document.iri === null,
);
</script>

<template>
  <section class="edition" aria-labelledby="document-edition">
    <h2 id="document-edition">{{ t("documents.page.edition.heading") }}</h2>
    <dl class="facts">
      <dt>{{ t("documents.page.edition.issuer") }}</dt>
      <dd>{{ document.issuer || t("documents.page.edition.none") }}</dd>
      <dt>{{ t("documents.page.edition.edition") }}</dt>
      <dd>{{ document.edition || t("documents.page.edition.none") }}</dd>
      <dt>{{ t("documents.page.edition.workHeading") }}</dt>
      <dd>{{ document.work ? workWords(document.work) : t("documents.page.edition.none") }}</dd>
      <dt>{{ t("documents.page.edition.iri") }}</dt>
      <dd class="edition__iri">{{ document.iri || t("documents.page.edition.noIri") }}</dd>
      <dt>{{ t("documents.page.edition.revision") }}</dt>
      <dd>{{ document.revision }}</dd>
    </dl>
    <DocumentMetaForm v-if="mayChange" :document="document" @changed="emit('changed')" />
    <!-- keyed: the works it knows are read once for the document it was made for -->
    <WorkForm v-if="maySetWork" :key="document.id" :document="document" @changed="emit('changed')" />
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

/* An IRI is one long word: it breaks rather than pushing the page sideways at 320px. */
.edition__iri {
  overflow-wrap: anywhere;
}
</style>
