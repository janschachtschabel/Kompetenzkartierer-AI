<script setup lang="ts">
import { computed } from "vue";

const props = defineProps<{
  title: string;
  body?: string;
  /**
   * The heading's level. 3 where the empty state sits in a section with a
   * heading of its own: at 2 the outline showed "nothing found" as a section
   * beside the one it belongs to (old app, audit 2026-09-26, E-104).
   */
  level?: 2 | 3;
}>();

const heading = computed(() => (props.level === 3 ? "h3" : "h2"));
</script>

<template>
  <div class="empty">
    <component :is="heading" class="empty__title">{{ title }}</component>
    <p v-if="body" class="empty__body">{{ body }}</p>
    <slot />
  </div>
</template>

<style scoped>
.empty {
  border: 1px dashed var(--border);
  border-radius: var(--radius);
  padding: var(--space-4);
  text-align: center;
  color: var(--text-muted);
}
.empty__title {
  margin: 0 0 var(--space-1);
  color: var(--text);
}
.empty__body {
  margin: 0 0 var(--space-2);
}
</style>
