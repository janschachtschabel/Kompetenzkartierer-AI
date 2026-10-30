<script setup lang="ts">
/**
 * A draft the tree closed on (plan M1 9.8, Paket 9c2 K6, 9c2b L4): why it is closed, as an alert, and what the
 * user changed or entered, field by field in words, to copy - with no form left to save it. The editor and
 * the form of a row to add show it alike, and take the keyboard to it (`focus`).
 */
import { computed, ref } from "vue";

import type { EditFields, FormField } from "@/api";
import AppIcon from "@/components/AppIcon.vue";
import { shownValue } from "@/formWords";
import { messages, t } from "@/i18n/de";
import { refusalText } from "@/refusals";
import { word } from "@/registerWords";

const props = defineProps<{ code: string; fields: FormField[]; changes: EditFields }>();

const section = ref<HTMLElement | null>(null);

// what the user changed, not what another did since
const kept = computed(() =>
  Object.entries(props.changes).map(([key, value]) => ({
    key,
    label: word(messages.documents.tree.fields, key),
    text: shownValue(props.fields, key, value),
  })),
);

/** The keyboard to it. */
function focus(): void {
  section.value?.focus();
}

defineExpose({ focus });
</script>

<template>
  <section ref="section" class="closed-draft" tabindex="-1" :aria-label="t('documents.tree.form.closedLabel')">
    <p class="field__error" role="alert"><AppIcon name="warning" /> {{ refusalText(code) }}</p>
    <p>{{ t("documents.tree.form.keptDraft") }}</p>
    <dl class="facts">
      <template v-for="entry in kept" :key="entry.key">
        <dt>{{ entry.label }}</dt>
        <dd><bdi>{{ entry.text }}</bdi></dd>
      </template>
    </dl>
  </section>
</template>

<style scoped>
.closed-draft {
  display: grid;
  gap: var(--space-1);
}

.closed-draft p {
  margin: 0;
}

/* A wording's lines and paragraphs kept, to copy as they were written. */
.closed-draft dd {
  white-space: pre-wrap;
}
</style>
