<script setup lang="ts">
/**
 * A node's or a statement's detail, as it reads (plan M1 9.7, Paket 9c J8): its fields in the order of the
 * sector's form, by their labels - the required ones always, "nicht angegeben" where empty, the others where
 * they hold a value - a list's values by their labels; where it comes from, its review status, its revision
 * and, once its document is frozen, its IRI; then its anchors, each able to show its page in the source.
 */
import { computed } from "vue";

import type { FieldValue, Form, FormField } from "@/api";
import AnchorFacts from "@/components/AnchorFacts.vue";
import type { Row } from "@/documentTree";
import { valueText } from "@/formWords";
import { messages, t } from "@/i18n/de";
import { CV, statusWord } from "@/reviewStatus";
import { conceptWord, word } from "@/registerWords";

const props = defineProps<{ row: Row; form: Form }>();
const emit = defineEmits<{ show: [page: number] }>();

const ORIGIN = `${CV}orig_`;

const item = computed(() => (props.row.kind === "node" ? props.row.node : props.row.statement));
const fields = computed<FormField[]>(() => (props.row.kind === "node" ? props.form.node : props.form.statement));

function filled(value: FieldValue | undefined): boolean {
  return Array.isArray(value) ? value.length > 0 : typeof value === "string" && value.trim() !== "";
}

const shown = computed(() =>
  fields.value
    .filter((field) => field.required || filled(item.value.fields[field.key]))
    .map((field) => {
      const value = item.value.fields[field.key] ?? null;
      let text = filled(value) ? valueText(fields.value, field.key, value) : t("documents.tree.notGiven");
      if (field.key === "code" && props.row.kind === "node" && props.row.node.code_assigned && filled(value)) {
        text = t("documents.tree.assignedCode", { code: text });
      }
      return { key: field.key, label: word(messages.documents.tree.fields, field.key), text, empty: !filled(value) };
    }),
);

const origin = computed(() => conceptWord(messages.documents.tree.origins, ORIGIN, item.value.origin));
</script>

<template>
  <div class="row-detail">
    <dl class="facts row-detail__fields">
      <template v-for="field in shown" :key="field.key">
        <dt>{{ field.label }}</dt>
        <dd :class="{ 'row-detail__empty': field.empty }">
          <bdi>{{ field.text }}</bdi>
        </dd>
      </template>
      <dt>{{ t("documents.tree.facts.origin") }}</dt>
      <dd>{{ origin }}</dd>
      <dt>{{ t("documents.tree.facts.status") }}</dt>
      <dd>{{ statusWord(item.review_status) }}</dd>
      <dt>{{ t("documents.tree.facts.revision") }}</dt>
      <dd>{{ item.revision }}</dd>
      <template v-if="item.iri">
        <dt>{{ t("documents.tree.facts.iri") }}</dt>
        <dd class="row-detail__iri">{{ item.iri }}</dd>
      </template>
    </dl>

    <h3>{{ t("documents.tree.anchors.heading") }}</h3>
    <ul v-if="item.anchors.length" class="row-detail__anchors">
      <li v-for="anchor in item.anchors" :key="anchor.id">
        <AnchorFacts :anchor="anchor" @show="(page) => emit('show', page)" />
      </li>
    </ul>
    <p v-else>{{ t("documents.tree.anchors.none") }}</p>
  </div>
</template>

<style scoped>
.row-detail {
  display: grid;
  gap: var(--space-2);
}

.row-detail__empty {
  color: var(--text-muted);
}

.row-detail__iri {
  font-family: var(--font-mono);
  font-size: var(--step--1);
  overflow-wrap: anywhere;
}

.row-detail__anchors {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  gap: var(--space-2);
}

.row-detail__anchors > li + li {
  border-block-start: 1px solid var(--border);
  padding-block-start: var(--space-2);
}
</style>
