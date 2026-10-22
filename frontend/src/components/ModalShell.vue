<script lang="ts">
// The frames open, the last opened on top: Escape is the top one's alone.
const openFrames: symbol[] = [];
</script>

<script setup lang="ts">
// The frame of a modal: the scrim, the dialog's role and its name, the Tab
// kept inside, Escape and a click on the scrim, and the keyboard given back
// to whatever opened it. Five dialogs had each written it out for themselves
// (old app, review D of the round "Sichtung", finding 8).
//
// What the dialog says, and where the keyboard starts in it, stay the
// dialog's own: a share dialog starts on its close button, an import on its
// file field. So does whether it may close now -- `close` is a request, and a
// dialog with a request out may turn it down.
//
// The keyboard's way back is learnt as the frame is mounted: before the
// dialog's own `onMounted`, which is where it moves the keyboard in.
import { onBeforeUnmount, onMounted, ref } from "vue";

import { trapTab } from "@/focusTrap";

defineProps<{
  /** The id of the dialog's heading, which names it. */
  labelledby: string;
  /** The id of what is read with the name as the dialog opens. */
  describedby?: string;
}>();

const emit = defineEmits<{ close: [] }>();

const dialog = ref<HTMLElement | null>(null);
const frame = Symbol("modal");
let previouslyFocused: HTMLElement | null = null;

onMounted(() => {
  previouslyFocused = document.activeElement as HTMLElement | null;
  openFrames.push(frame);
  document.addEventListener("keydown", onEscape);
});

onBeforeUnmount(() => {
  document.removeEventListener("keydown", onEscape);
  // Gone within the flush that mounted it, the frame never got on the stack:
  // splicing at -1 would take another frame off instead.
  const at = openFrames.indexOf(frame);
  if (at >= 0) openFrames.splice(at, 1);
  // The opener may be gone -- the row it sat in can be what was just removed.
  if (previouslyFocused?.isConnected) previouslyFocused.focus();
});

/**
 * Escape, heard on the whole page while the frame is open: a control that
 * went away drops the keyboard to the page's body, and heard on the dialog
 * alone, Escape then closed nothing (old app, review A2, pre-existing). Only the top
 * frame closes; a modal question of another kind asked over it -- a
 * ConfirmDialog -- answers Escape itself.
 */
function onEscape(event: KeyboardEvent): void {
  if (event.key !== "Escape" || openFrames.at(-1) !== frame) return;
  const target = event.target instanceof Element ? event.target : null;
  const modal = target?.closest("[aria-modal='true']");
  if (modal && modal !== dialog.value) return;
  emit("close");
}

function onKeydown(event: KeyboardEvent): void {
  trapTab(event, dialog.value);
}

// A click whose press began inside - a text selection let go past the dialog's edge - lands on
// the scrim as the common ancestor; only a press and a click both on the scrim close.
let pressedOnScrim = false;

function onScrimPress(event: MouseEvent): void {
  pressedOnScrim = event.target === event.currentTarget;
}

function onScrimClick(): void {
  if (pressedOnScrim) emit("close");
  pressedOnScrim = false;
}

defineExpose({ dialog });
</script>

<template>
  <div class="backdrop" @mousedown="onScrimPress" @click.self="onScrimClick">
    <div
      ref="dialog"
      class="dialog"
      role="dialog"
      aria-modal="true"
      :aria-labelledby="labelledby"
      :aria-describedby="describedby"
      @keydown="onKeydown"
    >
      <slot />
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
  max-width: 36rem;
  width: 100%;
  /* Within the scrim's padding on every side: a long dialog scrolls, its way
     out in reach, rather than pushing it off a phone's screen or at 200 %. */
  max-height: calc(100dvh - 2 * var(--space-2));
  overflow-y: auto;
}
</style>
