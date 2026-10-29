<script setup lang="ts">
/**
 * One anchor of a node's title or a statement (plan M1 9.9, Paket 9c J8): its page, how its passage was found
 * - in words, not as a colour - the passage, and the blocks of the document's conversion it names, with a way
 * to show its page in the source beside (SourcePane).
 */
import type { TreeAnchor } from "@/api";
import { matchText, pagesText } from "@/anchorWords";
import { t } from "@/i18n/de";

defineProps<{ anchor: TreeAnchor }>();
const emit = defineEmits<{ show: [page: number] }>();
</script>

<template>
  <div class="anchor">
    <dl class="facts">
      <dt>{{ t("documents.tree.anchors.where") }}</dt>
      <dd>{{ pagesText(anchor) }}</dd>
      <dt>{{ t("documents.tree.anchors.how") }}</dt>
      <dd>{{ matchText(anchor) }}</dd>
      <template v-if="anchor.quote">
        <dt>{{ t("documents.tree.anchors.quote") }}</dt>
        <dd>
          <bdi>{{ anchor.quote }}</bdi>
        </dd>
      </template>
      <template v-if="anchor.blocks.length">
        <dt>{{ t("documents.tree.anchors.blocks") }}</dt>
        <dd class="anchor__blocks">{{ anchor.blocks.join(", ") }}</dd>
      </template>
    </dl>
    <button
      v-if="anchor.page_start !== null"
      type="button"
      class="btn btn-sm secondary"
      @click="emit('show', anchor.page_start)"
    >
      {{ t("documents.tree.anchors.show", { page: anchor.page_start }) }}
    </button>
  </div>
</template>

<style scoped>
.anchor {
  display: grid;
  gap: var(--space-1);
  justify-items: start;
}

.anchor__blocks {
  font-family: var(--font-mono);
  font-size: var(--step--1);
}
</style>
