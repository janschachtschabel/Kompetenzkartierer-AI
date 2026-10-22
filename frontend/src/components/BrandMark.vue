<script setup lang="ts">
/**
 * The product's sign: a small map of four points and the paths between them -
 * what the app makes of curricula. Decorative: the name always stands beside it.
 */
withDefaults(defineProps<{ size?: number }>(), { size: 28 });
</script>

<template>
  <svg
    class="brand-mark"
    :width="size"
    :height="size"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    stroke-width="1.5"
    stroke-linecap="round"
    aria-hidden="true"
    focusable="false"
  >
    <path d="M6 7.5 17 6M6 7.5l6 9.5M17 6l-5 11M17 6l1.5 10.5M12 17l6.5-.5" />
    <circle class="brand-mark__point" cx="6" cy="7.5" r="2.25" />
    <circle class="brand-mark__point" cx="17" cy="6" r="2.25" />
    <circle class="brand-mark__point" cx="12" cy="17" r="2.25" />
    <circle class="brand-mark__point brand-mark__point--quiet" cx="18.5" cy="16.5" r="1.5" />
  </svg>
</template>

<style scoped>
.brand-mark {
  color: var(--accent);
  flex: none;
}

.brand-mark__point {
  fill: var(--accent);
}

/* The point not yet reached: outlined, not filled. */
.brand-mark__point--quiet {
  fill: var(--surface);
}
</style>
