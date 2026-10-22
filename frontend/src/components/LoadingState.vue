<script setup lang="ts">
import { t } from "@/i18n/de";

/**
 * `quiet`: shown, not said - where a status of the page's own says what the waiting brings, and a
 * live region here would say each time it starts again.
 */
defineProps<{ label?: string; quiet?: boolean }>();
</script>

<template>
  <p class="loading" :role="quiet ? undefined : 'status'" :aria-live="quiet ? undefined : 'polite'">
    <span class="spinner" aria-hidden="true"></span>
    {{ label ?? t("states.loading") }}
  </p>
</template>

<style scoped>
.loading {
  display: flex;
  align-items: center;
  gap: var(--space-1);
  color: var(--text-muted);
}
.spinner {
  width: 1em;
  height: 1em;
  border: 2px solid var(--border);
  border-top-color: var(--accent);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}
@media (prefers-reduced-motion: reduce) {
  .spinner {
    animation: none;
  }
}
@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
</style>
