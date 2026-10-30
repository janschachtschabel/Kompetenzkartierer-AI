<script setup lang="ts">
/**
 * The form of a row of a document's tree (plan M1 9.8, Paket 9c2 K2/K9): a field for each of the sector's form
 * (FormFieldInput), in its order; a list that hangs under another offers the values under its choice
 * (rowDraft.offeredValues). The draft goes back whole with each field changed; the button asks to save it,
 * and while it saves says it is busy without dropping the focus it holds. What else the draft holds - a
 * statement's anchors - stands in the slot, before the button.
 */
import type { FormField } from "@/api";
import FormFieldInput from "@/components/FormFieldInput.vue";
import { t } from "@/i18n/de";
import { offeredValues, type Draft } from "@/rowDraft";

const props = defineProps<{
  fields: FormField[];
  errors: Record<string, string>;
  saving: boolean;
  /** What its button does, where it does not save a change: adding a row. */
  saveLabel?: string;
}>();
const draft = defineModel<Draft>({ required: true });
const emit = defineEmits<{ submit: [] }>();

const inputs = new Map<string, InstanceType<typeof FormFieldInput>>();

function remember(key: string, input: unknown): void {
  if (input) inputs.set(key, input as InstanceType<typeof FormFieldInput>);
  else inputs.delete(key);
}

function change(key: string, value: string | string[]): void {
  draft.value = { ...draft.value, [key]: value };
}

function submit(): void {
  if (!props.saving) emit("submit");
}

/** The keyboard to the field `key`. */
function focusField(key: string): void {
  inputs.get(key)?.focus();
}

defineExpose({ focusField });
</script>

<template>
  <form class="row-form" novalidate @submit.prevent="submit">
    <FormFieldInput
      v-for="field in fields"
      :key="field.key"
      :ref="(input) => remember(field.key, input)"
      :field="field"
      :values="offeredValues(fields, field, draft)"
      :error="errors[field.key] ?? null"
      :model-value="draft[field.key] ?? (field.many ? [] : '')"
      @update:model-value="(value) => change(field.key, value)"
    />
    <slot />
    <!-- aria-disabled, not disabled: a disabled button drops the focus it holds -->
    <button type="submit" class="btn primary row-form__save" :aria-disabled="saving || undefined">
      {{ saveLabel ?? t("documents.tree.form.save") }}
    </button>
  </form>
</template>

<style scoped>
.row-form {
  display: grid;
}

.row-form__save {
  justify-self: start;
}
</style>
