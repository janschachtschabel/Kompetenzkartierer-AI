<script setup lang="ts">
/**
 * One row of a document's tree as its label (TreeView, plan M1 9.7): a node's code, title, type - its
 * function where it has none - and review status, with the number of its findings; a statement's wording,
 * kind and review status. What kind of row it is, is said to a screen reader first; the status is a word
 * beside its tone, never the tone alone.
 */
import { computed } from "vue";

import type { FieldValue, Form } from "@/api";
import type { Row } from "@/documentTree";
import { valueLabel } from "@/formWords";
import { t } from "@/i18n/de";
import { REVIEW_TONES, statusOf, statusWord } from "@/reviewStatus";

const props = defineProps<{ id: string; row: Row; form: Form }>();

function text(value: FieldValue | undefined): string | null {
  return typeof value === "string" && value.trim() ? value : null;
}

const status = computed(() => (props.row.kind === "node" ? props.row.node : props.row.statement).review_status);
const tone = computed(() => {
  const known = statusOf(status.value);
  return known ? REVIEW_TONES[known] : "neutral";
});

const node = computed(() => {
  if (props.row.kind !== "node") return null;
  const { fields, findings } = props.row.node;
  const type = text(fields.node_type);
  const named = type ?? text(fields.function);
  return {
    code: text(fields.code),
    title: text(fields.original_title) ?? t("documents.tree.untitled"),
    kind: named ? valueLabel(props.form.node, type ? "node_type" : "function", named) : null,
    findings: findings.violation + findings.warning + findings.info,
  };
});

const statement = computed(() => {
  if (props.row.kind !== "statement") return null;
  const { fields } = props.row.statement;
  const kind = text(fields.statement_kind);
  return {
    wording: text(fields.verbatim) ?? "",
    kind: kind ? valueLabel(props.form.statement, "statement_kind", kind) : null,
  };
});
</script>

<template>
  <span :id="id" class="tree-row">
    <span class="visually-hidden">{{ t(`documents.tree.kinds.${row.kind}`) }}</span>
    <template v-if="node">
      <span v-if="node.code" class="tree-row__code">{{ node.code }}</span>
      <bdi class="tree-row__title">{{ node.title }}</bdi>
      <span v-if="node.kind" class="tree-row__kind">{{ node.kind }}</span>
    </template>
    <template v-else-if="statement">
      <bdi class="tree-row__wording">{{ statement.wording }}</bdi>
      <span v-if="statement.kind" class="tree-row__kind">{{ statement.kind }}</span>
    </template>
    <span class="status-badge" :class="tone">{{ statusWord(status) }}</span>
    <span v-if="node && node.findings > 0" class="tree-row__findings">
      {{ t("documents.tree.findings", { count: node.findings }) }}
    </span>
  </span>
</template>

<style scoped>
.tree-row {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: var(--space-0) var(--space-1);
  min-width: 0;
}

.tree-row__code {
  font-family: var(--font-mono);
  font-size: var(--step--1);
}

.tree-row__title {
  font-weight: 600;
}

/* Two lines of a statement's wording in the tree; the detail shows it whole, and a screen reader reads it
   whole here too. */
.tree-row__wording {
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  overflow: hidden;
  flex: 1 1 18rem;
}

.tree-row__kind,
.tree-row__findings {
  color: var(--text-muted);
  font-size: var(--step--1);
}
</style>
