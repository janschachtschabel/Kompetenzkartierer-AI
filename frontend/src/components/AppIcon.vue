<script setup lang="ts">
/**
 * One icon, rendered.
 *
 * The drawings live in `@/icons` rather than here: a glyph table is data, and
 * keeping it in the component would mean the name type could not be exported
 * at all -- `<script setup>` carries no exports of its own.
 */
import { GLYPHS, type IconName } from "@/icons";

defineProps<{ name: IconName }>();
</script>

<template>
  <!-- Decorative without exception: an icon here always sits inside a control
       that carries its own name, whether as a visible label or a hidden one.
       `focusable="false"` because some engines still put an inline SVG in the
       tab order as a stop of its own, ahead of the button around it. -->
  <svg
    class="icon"
    :viewBox="'0 0 24 24'"
    width="1em"
    height="1em"
    fill="none"
    stroke="currentColor"
    stroke-width="1.5"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
    focusable="false"
  >
    <path v-for="d in GLYPHS[name]" :key="d" :d="d" />
  </svg>
</template>

<style scoped>
.icon {
  /* Never squeezed by a flex row it shares with a long German label. */
  flex: none;
  /* Sits on the text baseline when it is used inline rather than in a flex row. */
  vertical-align: -0.125em;
}
</style>
