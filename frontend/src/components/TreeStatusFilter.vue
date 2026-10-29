<script setup lang="ts">
/**
 * The tree's filter by review status (plan M1 9.7, Paket 9c J7): a toggle per status with the number of nodes
 * and statements of it in the whole document - the server's counts: a count that shrank as you filtered
 * would say nothing about the document - every status offered at nought too. Several may be on at once;
 * none on shows all.
 */
import { computed, nextTick, ref } from "vue";

import AppIcon from "@/components/AppIcon.vue";
import { t } from "@/i18n/de";
import { REVIEW_STATUSES, statusIri, statusWord } from "@/reviewStatus";

const props = defineProps<{ counts: { nodes: Record<string, number>; statements: Record<string, number> } }>();
const selected = defineModel<Set<string>>({ required: true });

const options = computed(() =>
  REVIEW_STATUSES.map((status) => {
    const iri = statusIri(status);
    return {
      iri,
      text: t("documents.tree.filter.option", {
        label: statusWord(iri),
        nodes: props.counts.nodes[iri] ?? 0,
        statements: props.counts.statements[iri] ?? 0,
      }),
    };
  }),
);

const group = ref<HTMLElement | null>(null);

// "all" goes as it is pressed: the keyboard stays in the filter, on its first toggle
function showAll(): void {
  selected.value = new Set();
  void nextTick(() => group.value?.querySelector("button")?.focus());
}

function toggle(iri: string): void {
  const next = new Set(selected.value);
  if (!next.delete(iri)) next.add(iri);
  selected.value = next;
}
</script>

<template>
  <div ref="group" class="status-filter" role="group" :aria-label="t('documents.tree.filter.label')">
    <button
      v-for="option in options"
      :key="option.iri"
      type="button"
      class="btn btn-sm secondary"
      :aria-pressed="selected.has(option.iri) ? 'true' : 'false'"
      @click="toggle(option.iri)"
    >
      <!-- its room kept while off, so the row of toggles does not shift -->
      <span class="status-filter__tick" aria-hidden="true">
        <AppIcon v-if="selected.has(option.iri)" name="check" />
      </span>
      {{ option.text }}
    </button>
    <button v-if="selected.size > 0" type="button" class="btn link" @click="showAll">
      {{ t("documents.tree.filter.all") }}
    </button>
  </div>
</template>

<style scoped>
.status-filter {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-1);
}

.status-filter__tick {
  display: inline-flex;
  inline-size: 1em;
}
</style>
