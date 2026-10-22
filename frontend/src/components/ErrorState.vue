<script setup lang="ts">
import AppIcon from "@/components/AppIcon.vue";
import NoticeText from "@/components/NoticeText.vue";
import { t } from "@/i18n/de";

// `reason` is the server's own sentence, shown after the message as an
// English quotation; `explanation` the page's own words for a refusal the
// server named by its code, shown instead (see notice.ts).
defineProps<{ message: string; reason?: string; explanation?: string }>();
defineEmits<{ retry: [] }>();
</script>

<template>
  <div class="error" role="alert">
    <p class="error__message">
      <AppIcon class="error__icon" name="warning" />
      <NoticeText :notice="{ text: message, reason, explanation }" />
    </p>
    <button type="button" class="btn primary" @click="$emit('retry')">
      {{ t("states.retry") }}
    </button>
  </div>
</template>

<style scoped>
.error {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  align-items: flex-start;
}
.error__message {
  display: flex;
  gap: var(--space-1);
  color: var(--danger);
  margin: 0;
}
</style>
