<script setup lang="ts">
/**
 * The editor of a row of a document's tree (plan M1 9.8, Paket 9c2 K4-K7): its form (RowForm) and how a save
 * went (rowSave.ts) - saved, nothing to save, a change met another (ConflictPanel, the keyboard taken there),
 * a field's problem (the keyboard to the field), a failure above the form. Where the tree closed meanwhile it
 * says why and keeps the draft to copy, with no form left to save it - so too where the tree, read anew,
 * closed under the draft (`closedBy`). It tells the view whether a draft is open (the leave guard; none once
 * it is gone) and when a save changed the tree, closed it or found the row gone.
 */
import { computed, nextTick, onBeforeUnmount, ref, toRef, watch } from "vue";

import type { Form } from "@/api";
import AppIcon from "@/components/AppIcon.vue";
import ConflictPanel from "@/components/ConflictPanel.vue";
import NoticeText from "@/components/NoticeText.vue";
import RowForm from "@/components/RowForm.vue";
import type { Row } from "@/documentTree";
import { shownValue } from "@/formWords";
import { messages, t } from "@/i18n/de";
import { sayAnew } from "@/liveRegion";
import { refusalText } from "@/refusals";
import { word } from "@/registerWords";
import { changedFields } from "@/rowDraft";
import { useRowSave, type SaveOutcome } from "@/rowSave";

const props = defineProps<{
  row: Row;
  form: Form;
  /** Why the tree, read anew, closed while a draft was open; none while it is open. */
  closedBy?: string | null;
  /**
   * A change saved. A prop, not an event: a save that lands after another row was chosen - this editor
   * unmounted meanwhile, its events no longer heard - still has the tree read anew.
   */
  onSaved?: () => void;
}>();
const emit = defineEmits<{ closed: [code: string]; gone: []; dirty: [open: boolean] }>();

const editing = useRowSave(toRef(props, "row"), toRef(props, "form"));
const { fields, before, draft, saving, errors, problem, conflict, closed, dirty } = editing;
const status = ref("");
const formRef = ref<InstanceType<typeof RowForm> | null>(null);
const panel = ref<InstanceType<typeof ConflictPanel> | null>(null);
const closedNotice = ref<HTMLElement | null>(null);
// the tree closed: on this save, or under the draft as it was read anew
const shut = computed(() => closed.value ?? props.closedBy ?? null);

// the draft the tree closed on, in words, field by field: what the user changed, not what another did since
const kept = computed(() => {
  const changed = changedFields(fields.value, before.value, draft.value);
  return Object.entries(changed).map(([key, value]) => ({
    key,
    label: word(messages.documents.tree.fields, key),
    text: shownValue(fields.value, key, value),
  }));
});

watch(dirty, (open) => emit("dirty", open), { immediate: true });
// gone with its row, its document or its tree: no draft left to ask about
onBeforeUnmount(() => emit("dirty", false));

async function submit(): Promise<void> {
  const outcome = await editing.save();
  await nextTick();
  // said anew after each click, so that the same words are read again
  const said: Partial<Record<SaveOutcome, string>> = {
    saved: t("documents.tree.form.saved"),
    unchanged: t("documents.tree.form.unchanged"),
    undecided: t("documents.tree.conflict.undecided"),
  };
  const words = said[outcome];
  status.value = words ? sayAnew(status.value, words) : "";
  if (outcome === "saved") props.onSaved?.();
  else if (outcome === "conflict" || outcome === "undecided") panel.value?.focus();
  else if (outcome === "invalid") {
    const first = Object.keys(errors.value)[0];
    if (first) formRef.value?.focusField(first);
  } else if (outcome === "closed" && closed.value) {
    closedNotice.value?.focus();
    emit("closed", closed.value);
  } else if (outcome === "gone") emit("gone");
}
</script>

<template>
  <div class="row-editor">
    <section
      v-if="shut"
      ref="closedNotice"
      class="row-editor__closed"
      tabindex="-1"
      :aria-label="t('documents.tree.form.closedLabel')"
    >
      <p class="field__error" role="alert"><AppIcon name="warning" /> {{ refusalText(shut) }}</p>
      <p>{{ t("documents.tree.form.keptDraft") }}</p>
      <dl class="facts">
        <template v-for="entry in kept" :key="entry.key">
          <dt>{{ entry.label }}</dt>
          <dd><bdi>{{ entry.text }}</bdi></dd>
        </template>
      </dl>
    </section>
    <template v-else>
      <p v-if="problem" class="field__error row-editor__problem" role="alert">
        <AppIcon name="warning" /> <NoticeText :notice="problem" />
      </p>
      <ConflictPanel
        v-if="conflict"
        ref="panel"
        :fields="fields"
        :clashes="conflict.clashes"
        :taken="conflict.taken"
        :stored="conflict.stored"
        @keep="editing.keep"
        @take="editing.take"
      />
      <RowForm ref="formRef" v-model="draft" :fields="fields" :errors="errors" :saving="saving" @submit="submit" />
    </template>
    <!-- always in the page, so the first word is read out -->
    <p class="row-editor__status" role="status">{{ status }}</p>
  </div>
</template>

<style scoped>
.row-editor {
  display: grid;
  gap: var(--space-1);
}

.row-editor__closed {
  display: grid;
  gap: var(--space-1);
}

.row-editor__closed p,
.row-editor__status {
  margin: 0;
}

/* A wording's lines and paragraphs kept, to copy as they were written. */
.row-editor__closed dd {
  white-space: pre-wrap;
}
</style>
