<script setup lang="ts">
/**
 * A notice's German sentence, and why after it: the page's own words for a
 * refusal it knows, or the server's reason, quoted and marked as English (see
 * notice.ts). Renders nothing for no notice, so a live region can hold it from
 * the start and be filled later.
 */
import type { Notice } from "@/notice";

defineProps<{ notice?: Notice | null }>();
</script>

<template>
  <span v-if="notice">{{ notice.text }} <template v-if="notice.explanation">{{ notice.explanation }}</template><q v-else-if="notice.reason" lang="en">{{ notice.reason }}</q></span>
</template>
