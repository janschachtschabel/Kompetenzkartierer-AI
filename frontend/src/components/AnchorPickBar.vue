<script setup lang="ts">
/**
 * What choosing a statement's anchor in the source offers (plan M1 9.8, Paket 9c2b L3): how to, taking the
 * blocks chosen - their count in its name, refused while there are none - and taking the page shown as one
 * the passage was not found on. Which blocks are chosen is the source's (anchorPick.ts).
 */
import { t } from "@/i18n/de";

defineProps<{ count: number; page: number }>();
const emit = defineEmits<{ take: []; notFound: [] }>();
</script>

<template>
  <div class="anchor-pick">
    <p class="anchor-pick__note">{{ t("documents.tree.source.pickNote") }}</p>
    <!-- aria-disabled, not disabled: the button keeps the keyboard it holds once its blocks are taken -->
    <button
      type="button"
      class="btn btn-sm secondary"
      data-test="take"
      :aria-disabled="count ? undefined : 'true'"
      @click="count && emit('take')"
    >
      {{ t("documents.tree.source.take", { count }) }}
    </button>
    <button type="button" class="btn btn-sm secondary" data-test="not-found" @click="emit('notFound')">
      {{ t("documents.tree.source.notFound", { page }) }}
    </button>
  </div>
</template>

<style scoped>
.anchor-pick {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-1);
}

.anchor-pick__note {
  flex-basis: 100%;
  margin: 0;
  color: var(--text-muted);
  font-size: var(--step--1);
}
</style>
