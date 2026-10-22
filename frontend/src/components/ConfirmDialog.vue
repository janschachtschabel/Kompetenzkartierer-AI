<script setup lang="ts">
// A modal question for destructive actions. It owns the three things a custom
// dialog has to get right and a native confirm() gets for free: focus moves in,
// stays in while open, and returns to whatever opened it.
//
// Focus starts on Cancel, not on the destructive button, so Enter on a dialog
// that appeared unexpectedly does not delete anything. A question whose first
// step is a choice (`focusFirst`) starts on that choice instead.
import { nextTick, onBeforeUnmount, onMounted, ref } from "vue";

import { focusablesIn, trapTab } from "@/focusTrap";
import { t } from "@/i18n/de";

const props = defineProps<{
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
}>();

const emit = defineEmits<{ confirm: []; cancel: [] }>();

const dialog = ref<HTMLElement | null>(null);
const cancelButton = ref<HTMLButtonElement | null>(null);
let previouslyFocused: HTMLElement | null = null;

onMounted(async () => {
  previouslyFocused = document.activeElement as HTMLElement | null;
  await nextTick();
  (props.focusFirst ? focusablesIn(dialog.value)[0] : cancelButton.value)?.focus();
});

onBeforeUnmount(() => {
  // The trigger may be gone -- the row it sat in can be what was just deleted.
  if (previouslyFocused?.isConnected) previouslyFocused.focus();
});

function onKeydown(event: KeyboardEvent): void {
  if (event.key === "Escape") {
    emit("cancel");
    return;
  }
  trapTab(event, dialog.value);
}
</script>

<template>
  <div class="backdrop" @click.self="emit('cancel')">
    <div
      ref="dialog"
      class="dialog"
      role="dialog"
      aria-modal="true"
      aria-labelledby="confirm-title"
      :aria-describedby="describedBy ? `confirm-message ${describedBy}` : 'confirm-message'"
      @keydown="onKeydown"
    >
      <h2 id="confirm-title" class="dialog__title">{{ title }}</h2>
      <p id="confirm-message" class="dialog__message">{{ message }}</p>
      <!-- Whatever the question needs beyond its sentence: a choice of options. -->
      <slot />
      <div class="dialog__actions">
        <button
          ref="cancelButton"
          type="button"
          class="dialog__button"
          data-test="cancel"
          @click="emit('cancel')"
        >
          {{ t("dialog.cancel") }}
        </button>
        <button
          type="button"
          class="dialog__button"
          :class="danger === false ? 'dialog__button--primary' : 'dialog__button--danger'"
          data-test="confirm"
          :disabled="confirmDisabled"
          @click="emit('confirm')"
        >
          {{ confirmLabel ?? t("dialog.confirm") }}
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.backdrop {
  position: fixed;
  inset: 0;
  background: var(--scrim);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--space-2);
  z-index: 50;
}

.dialog {
  background: var(--surface);
  color: var(--text);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: var(--space-3);
  max-width: 32rem;
  width: 100%;
  /* Within the backdrop's padding on every side: a question with many
     options scrolls instead of pushing its buttons off the screen. */
  max-height: calc(100dvh - 2 * var(--space-2));
  overflow-y: auto;
}

.dialog__title {
  margin: 0 0 var(--space-1);
  font-size: 1.1rem;
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

.dialog__button {
  min-height: 2.75rem;
  padding: 0 var(--space-2);
  border: 1px solid var(--control-border);
  border-radius: var(--radius);
  background: var(--surface);
  color: var(--text);
  cursor: pointer;
}

.dialog__button:hover {
  background: var(--surface-subtle);
}

.dialog__button--danger {
  background: var(--danger-solid);
  border-color: var(--danger-solid);
  color: var(--danger-contrast);
}

.dialog__button--danger:hover {
  filter: brightness(0.92);
}

.dialog__button--primary {
  background: var(--accent);
  border-color: var(--accent);
  color: var(--accent-contrast);
}

.dialog__button--primary:hover:not(:disabled) {
  background: var(--accent-hover);
}

.dialog__button:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
</style>
