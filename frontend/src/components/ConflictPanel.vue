<script setup lang="ts">
/**
 * A change laid beside the row as another stored it meanwhile (plan M1 9.8, Paket 9c2 K5; after the old app's
 * NodeConflict.vue, rowConflict.ts works it out): each field both changed, the user's value and the stored one
 * in words - an empty one as such - with the choice to keep theirs or take the stored; the fields taken in
 * because only the other changed them, named with their values. Once a field is decided the keyboard goes on
 * to the next; with none left, to the panel, whose intro says to save again. The editor takes the keyboard
 * to the panel as it appears (`focus`).
 */
import { nextTick, ref, useId, watch } from "vue";

import type { FormField } from "@/api";
import { shownValue } from "@/formWords";
import { messages, t } from "@/i18n/de";
import { word } from "@/registerWords";
import type { Clash } from "@/rowConflict";
import type { Draft } from "@/rowDraft";

const props = defineProps<{ fields: FormField[]; clashes: Clash[]; taken: string[]; stored: Draft }>();
const emit = defineEmits<{ keep: [key: string]; take: [key: string] }>();

const id = useId();
const section = ref<HTMLElement | null>(null);
// the place of the field last decided, where the keyboard goes on once the list is shorter
let decided: number | null = null;

function label(key: string): string {
  return word(messages.documents.tree.fields, key);
}

function shown(key: string, value: string | string[] | undefined): string {
  return shownValue(props.fields, key, value);
}

function decide(index: number, key: string, how: "keep" | "take"): void {
  decided = index;
  if (how === "keep") emit("keep", key);
  else emit("take", key);
}

watch(
  () => props.clashes,
  async (now) => {
    if (decided === null) return;
    const at = Math.min(decided, now.length - 1);
    decided = null;
    await nextTick();
    if (at < 0) section.value?.focus();
    else section.value?.querySelectorAll(".conflict-panel__clash")[at]?.querySelector("button")?.focus();
  },
);

/** The keyboard to the panel. */
function focus(): void {
  section.value?.focus();
}

defineExpose({ focus });
</script>

<template>
  <!-- focused as it appears, read with its intro: what to do -->
  <section
    ref="section"
    class="conflict-panel"
    tabindex="-1"
    :aria-labelledby="`${id}-heading`"
    :aria-describedby="`${id}-intro`"
  >
    <h3 :id="`${id}-heading`">{{ t("documents.tree.conflict.heading") }}</h3>
    <p :id="`${id}-intro`" class="conflict-panel__intro">
      {{ clashes.length ? t("documents.tree.conflict.intro") : t("documents.tree.conflict.introNothing") }}
    </p>
    <ul v-if="clashes.length" class="conflict-panel__list">
      <li v-for="(clash, index) in clashes" :key="clash.key" class="conflict-panel__clash">
        <p :id="`${id}-${clash.key}`" class="conflict-panel__field">{{ label(clash.key) }}</p>
        <dl class="conflict-panel__values">
          <div>
            <dt>{{ t("documents.tree.conflict.yours") }}</dt>
            <dd><bdi>{{ shown(clash.key, clash.yours) }}</bdi></dd>
          </div>
          <div>
            <dt>{{ t("documents.tree.conflict.stored") }}</dt>
            <dd><bdi>{{ shown(clash.key, clash.stored) }}</bdi></dd>
          </div>
        </dl>
        <span class="conflict-panel__actions">
          <button
            type="button"
            class="btn btn-sm secondary"
            :aria-describedby="`${id}-${clash.key}`"
            @click="decide(index, clash.key, 'keep')"
          >
            {{ t("documents.tree.conflict.keep") }}
          </button>
          <button
            type="button"
            class="btn btn-sm secondary"
            :aria-describedby="`${id}-${clash.key}`"
            @click="decide(index, clash.key, 'take')"
          >
            {{ t("documents.tree.conflict.take") }}
          </button>
        </span>
      </li>
    </ul>
    <div v-if="taken.length" class="conflict-panel__taken">
      <p>{{ t("documents.tree.conflict.taken") }}</p>
      <ul>
        <li v-for="key in taken" :key="key">{{ label(key) }}: <bdi>{{ shown(key, stored[key]) }}</bdi></li>
      </ul>
    </div>
  </section>
</template>

<style scoped>
.conflict-panel {
  display: grid;
  gap: var(--space-1);
  padding: var(--space-2);
  border: 1px solid var(--border);
  border-inline-start: 3px solid var(--warning);
  border-radius: var(--radius);
}

.conflict-panel h3,
.conflict-panel p {
  margin: 0;
}

.conflict-panel__list {
  display: grid;
  gap: var(--space-2);
  margin: 0;
  padding: 0;
  list-style: none;
}

.conflict-panel__field {
  font-weight: 600;
}

.conflict-panel__values {
  display: grid;
  gap: var(--space-0);
  margin: var(--space-0) 0;
}

.conflict-panel__values div {
  display: grid;
  grid-template-columns: minmax(6rem, auto) minmax(0, 1fr);
  gap: var(--space-1);
}

.conflict-panel__values dt {
  color: var(--text-muted);
}

.conflict-panel__values dd,
.conflict-panel__taken li {
  margin: 0;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.conflict-panel__actions {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-1);
}

.conflict-panel__taken ul {
  margin: var(--space-0) 0 0;
}
</style>
