<script setup lang="ts">
/**
 * The anchors of a statement's draft (plan M1 9.8, Paket 9c2b L3/L8): each in words (anchorDraft.ts), with a
 * button to remove it that names which; with none, how to choose one in the source. A problem of the anchors
 * stands under them and describes the list, which the editor takes the keyboard to (`focus`). Once one is
 * removed the keyboard goes on to the one in its place, the one before where it was the last, the list where
 * none is left.
 */
import { nextTick, ref, useId, watch } from "vue";

import { anchorCodeText } from "@/anchorDraft";
import AppIcon from "@/components/AppIcon.vue";
import { t } from "@/i18n/de";

const props = defineProps<{ codes: string[]; error?: string | null }>();
const emit = defineEmits<{ remove: [code: string] }>();

const id = useId();
const errorId = `${id}-error`;
const section = ref<HTMLElement | null>(null);
// the place of the anchor last removed, where the keyboard goes on once the list is shorter
let removed: number | null = null;

function remove(index: number, code: string): void {
  removed = index;
  emit("remove", code);
}

watch(
  () => props.codes,
  async (now) => {
    if (removed === null) return;
    const at = Math.min(removed, now.length - 1);
    removed = null;
    await nextTick();
    if (at < 0) section.value?.focus();
    else section.value?.querySelectorAll<HTMLButtonElement>("li button")[at]?.focus();
  },
);

/** The keyboard to the list. */
function focus(): void {
  section.value?.focus();
}

defineExpose({ focus });
</script>

<template>
  <!-- tabindex -1: where the keyboard goes for a problem of the anchors, or once none is left -->
  <section
    ref="section"
    class="anchor-draft"
    tabindex="-1"
    :aria-labelledby="`${id}-heading`"
    :aria-describedby="error ? errorId : undefined"
  >
    <h3 :id="`${id}-heading`">{{ t("documents.tree.anchors.draftHeading") }}</h3>
    <ul v-if="codes.length" class="anchor-draft__list">
      <li v-for="(code, index) in codes" :key="code">
        <span :id="`${id}-${index}`">{{ anchorCodeText(code) }}</span>
        <button
          type="button"
          class="btn btn-sm secondary"
          :aria-describedby="`${id}-${index}`"
          @click="remove(index, code)"
        >
          {{ t("documents.tree.anchors.remove") }}
        </button>
      </li>
    </ul>
    <p v-else>{{ t("documents.tree.anchors.draftNone") }}</p>
    <p v-if="error" :id="errorId" class="field__error"><AppIcon name="warning" /> {{ error }}</p>
  </section>
</template>

<style scoped>
/* clear of the button that saves, as a field of the form is */
.anchor-draft {
  display: grid;
  gap: var(--space-1);
  margin-block-end: var(--space-2);
}

.anchor-draft h3,
.anchor-draft p {
  margin: 0;
}

.anchor-draft__list {
  display: grid;
  gap: var(--space-1);
  margin: 0;
  padding: 0;
  list-style: none;
}

.anchor-draft__list li {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-1);
}
</style>
