<script setup lang="ts">
/**
 * Part of the page is there, part is not: what is missing, said beside what is
 * shown. A status, not an alert - nothing stopped working - with the way to
 * fetch the rest where the page has one. The words go through a Notice, so a
 * refusal the page knows is said in German and the server's reason is quoted.
 */
import AppIcon from "@/components/AppIcon.vue";
import NoticeText from "@/components/NoticeText.vue";
import { t } from "@/i18n/de";
import type { Notice } from "@/notice";

defineProps<{ notice: Notice; retry?: boolean }>();
defineEmits<{ retry: [] }>();
</script>

<template>
  <div class="page-notice" role="status">
    <div class="page-notice__row">
      <p class="page-notice__text"><AppIcon name="warning" /> <NoticeText :notice="notice" /></p>
      <button v-if="retry" type="button" class="btn secondary btn-sm" @click="$emit('retry')">
        {{ t("states.retry") }}
      </button>
    </div>
  </div>
</template>
