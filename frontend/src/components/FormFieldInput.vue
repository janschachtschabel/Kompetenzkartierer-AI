<script setup lang="ts">
/**
 * One field of a row's form (plan M1 9.8, Paket 9c2 K9), built from the sector's form: a text in a box as long
 * as the form allows, a long text in a text area, one value of a list in a select, several in a group of
 * boxes. A required field says so in its label's words. A value the form does not know - retired from the
 * vocabulary since it was written - stays a choice of its own, so that saving does not drop it unasked. A
 * problem the server names stands at the field, tied to its control, with the warning sign beside the words.
 */
import { computed, ref, useId } from "vue";

import type { FormField, FormValue } from "@/api";
import { isolate } from "@/bidi";
import AppIcon from "@/components/AppIcon.vue";
import { messages, t } from "@/i18n/de";
import { word } from "@/registerWords";

const props = defineProps<{ field: FormField; values: FormValue[]; error?: string | null }>();
const model = defineModel<string | string[]>({ required: true });

const id = useId();
const errorId = `${id}-error`;
const control = ref<HTMLElement | null>(null);
const group = ref<HTMLElement | null>(null);

const name = computed(() => {
  const label = word(messages.documents.tree.fields, props.field.key);
  return props.field.required ? t("documents.tree.form.requiredLabel", { label }) : label;
});
// the values held that the form does not know
const unknown = computed(() => {
  const held = Array.isArray(model.value) ? model.value : model.value ? [model.value] : [];
  return held.filter((iri) => !props.values.some((value) => value.iri === iri));
});
// the boxes of a field of many: the values offered, then those held the form does not know
const boxes = computed(() => [
  ...props.values.map((value) => ({ iri: value.iri, label: value.label })),
  ...unknown.value.map((iri) => ({ iri, label: unknownLabel(iri) })),
]);
const described = computed(() => (props.error ? errorId : undefined));

// an IRI set apart from the words around it: its own direction does not turn them
function unknownLabel(iri: string): string {
  return t("documents.tree.form.unknownValue", { iri: isolate(iri) });
}

function focus(): void {
  (control.value ?? group.value?.querySelector("input"))?.focus();
}

defineExpose({ focus });
</script>

<template>
  <fieldset v-if="field.many" ref="group" class="form-field__group" :aria-describedby="described">
    <legend>{{ name }}</legend>
    <div v-for="(box, index) in boxes" :key="box.iri" class="field checkbox-field">
      <!-- each box says it too: a screen reader reads the box focused, not always its group -->
      <input
        :id="`${id}-${index}`"
        v-model="model"
        type="checkbox"
        :value="box.iri"
        :aria-invalid="error ? true : undefined"
        :aria-describedby="described"
      />
      <label :for="`${id}-${index}`">{{ box.label }}</label>
    </div>
    <p v-if="error" :id="errorId" class="field__error"><AppIcon name="warning" /> {{ error }}</p>
  </fieldset>
  <div v-else class="field">
    <label :for="id">{{ name }}</label>
    <select
      v-if="field.kind === 'concept'"
      :id="id"
      ref="control"
      v-model="model"
      :aria-invalid="error ? true : undefined"
      :aria-describedby="described"
    >
      <option v-if="!field.required || !model" value="">
        {{ field.required ? t("documents.tree.form.choose") : t("documents.tree.form.none") }}
      </option>
      <option v-for="value in values" :key="value.iri" :value="value.iri">{{ value.label }}</option>
      <option v-for="iri in unknown" :key="iri" :value="iri">{{ unknownLabel(iri) }}</option>
    </select>
    <textarea
      v-else-if="field.kind === 'longtext'"
      :id="id"
      ref="control"
      v-model="model"
      rows="4"
      :maxlength="field.most ?? undefined"
      :aria-invalid="error ? true : undefined"
      :aria-describedby="described"
    ></textarea>
    <input
      v-else
      :id="id"
      ref="control"
      v-model="model"
      type="text"
      :maxlength="field.most ?? undefined"
      :aria-invalid="error ? true : undefined"
      :aria-describedby="described"
    />
    <p v-if="error" :id="errorId" class="field__error"><AppIcon name="warning" /> {{ error }}</p>
  </div>
</template>

<style scoped>
.form-field__group {
  margin: 0 0 var(--space-2);
  padding: 0;
  border: 0;
}

.form-field__group legend {
  padding: 0;
  margin-block-end: var(--space-0);
  font-size: var(--step--1);
  font-weight: 500;
}

.form-field__group .field {
  margin-block-end: var(--space-0);
}

/* An IRI as a box's label breaks anywhere rather than widen the page (SC 1.4.10). */
.form-field__group label {
  overflow-wrap: anywhere;
}
</style>
