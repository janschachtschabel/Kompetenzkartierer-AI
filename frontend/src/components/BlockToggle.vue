<script setup lang="ts">
/**
 * A block of the source as a toggle while a statement's anchor is chosen (plan M1 9.8, Paket 9c2b L3): named by
 * the block's id, pressed - with a tick, not by colour alone - once chosen. Whether it is, is the caller's.
 */
import AppIcon from "@/components/AppIcon.vue";
import { t } from "@/i18n/de";

defineProps<{ id: string; pressed: boolean }>();
const emit = defineEmits<{ toggle: [] }>();
</script>

<template>
  <button
    type="button"
    class="btn btn-sm secondary block-toggle"
    :aria-pressed="pressed ? 'true' : 'false'"
    :aria-label="t('documents.tree.source.pick', { id })"
    @click="emit('toggle')"
  >
    <!-- its room kept while off, so the line does not shift -->
    <span class="block-toggle__tick" aria-hidden="true"><AppIcon v-if="pressed" name="check" /></span>
    {{ t("documents.tree.source.pickLabel") }}
  </button>
</template>

<style scoped>
.block-toggle {
  margin-inline-start: auto;
}

.block-toggle__tick {
  display: inline-flex;
  inline-size: 1em;
}
</style>
