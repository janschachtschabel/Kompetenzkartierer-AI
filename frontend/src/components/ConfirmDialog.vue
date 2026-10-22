<script setup lang="ts">
// A modal question, by default before a destructive action. The frame - scrim,
// role, the Tab kept inside, Escape on the whole page, the keyboard given back
// to whatever opened it - is ModalShell's; this owns the question, its two
// answers and where the keyboard starts.
//
// Focus starts on Cancel, not on the destructive button, so Enter on a dialog
// that appeared unexpectedly does not delete anything. A question whose first
// step is a choice (`focusFirst`) starts on that choice instead.
import { nextTick, onMounted, ref } from "vue";

import ModalShell from "@/components/ModalShell.vue";
import { focusablesIn } from "@/focusTrap";
import { t } from "@/i18n/de";

const props = withDefaults(
  defineProps<{
    title: string;
    message: string;
    confirmLabel?: string;
    /** False for a question whose answer adds something rather than removes it. */
    danger?: boolean;
    confirmDisabled?: boolean;
    /** The id of what the slot says beyond the sentence, read with it as the dialog opens. */
    describedBy?: string;
    /** Start on the first control of the slot rather than on Cancel. */
    focusFirst?: boolean;
  }>(),
  // a boolean prop left out is false: the destructive default has to be said
  { danger: true },
);

const emit = defineEmits<{ confirm: []; cancel: [] }>();

const shell = ref<InstanceType<typeof ModalShell> | null>(null);
const cancelButton = ref<HTMLButtonElement | null>(null);

onMounted(async () => {
  await nextTick();
  (props.focusFirst ? focusablesIn(shell.value?.dialog ?? null)[0] : cancelButton.value)?.focus();
});
</script>

<template>
  <ModalShell
    ref="shell"
    labelledby="confirm-title"
    :describedby="describedBy ? `confirm-message ${describedBy}` : 'confirm-message'"
    @close="emit('cancel')"
  >
    <h2 id="confirm-title" class="dialog__title">{{ title }}</h2>
    <p id="confirm-message" class="dialog__message">{{ message }}</p>
    <!-- Whatever the question needs beyond its sentence: a choice of options. -->
    <slot />
    <div class="dialog__actions">
      <button ref="cancelButton" type="button" class="btn secondary" data-test="cancel" @click="emit('cancel')">
        {{ t("dialog.cancel") }}
      </button>
      <button
        type="button"
        class="btn"
        :class="danger ? 'danger' : 'primary'"
        data-test="confirm"
        :disabled="confirmDisabled"
        @click="emit('confirm')"
      >
        {{ confirmLabel ?? t("dialog.confirm") }}
      </button>
    </div>
  </ModalShell>
</template>

<style scoped>
.dialog__title {
  margin: 0 0 var(--space-1);
  font-size: var(--step-1);
}

.dialog__message {
  margin: 0 0 var(--space-3);
  color: var(--text-muted);
}

.dialog__actions {
  display: flex;
  justify-content: flex-end;
  gap: var(--space-1);
  flex-wrap: wrap;
}
</style>
