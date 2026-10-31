<script setup lang="ts">
/**
 * The question before a document is frozen (plan M1 9.10, Paket 9d1 N6; after the old app's RunFreezeDialog): it
 * names the document and its revision and lists what follows, read with the question as it opens; the keyboard
 * starts on Cancel, Escape counts as Cancel (ConfirmDialog).
 */
import { useId } from "vue";

import { isolate } from "@/bidi";
import ConfirmDialog from "@/components/ConfirmDialog.vue";
import { t } from "@/i18n/de";

defineProps<{ title: string; revision: number }>();
const emit = defineEmits<{ confirm: []; cancel: [] }>();

const listId = useId();
</script>

<template>
  <ConfirmDialog
    :title="t('documents.page.freeze.title')"
    :message="t('documents.page.freeze.message', { title: isolate(title), revision })"
    :confirm-label="t('documents.page.freeze.button')"
    :described-by="listId"
    @confirm="emit('confirm')"
    @cancel="emit('cancel')"
  >
    <ul :id="listId" class="freeze-dialog__list">
      <li>{{ t("documents.page.freeze.follows.iris") }}</li>
      <li>{{ t("documents.page.freeze.follows.fixed") }}</li>
      <li>{{ t("documents.page.freeze.follows.noJobs") }}</li>
      <li>{{ t("documents.page.freeze.follows.copy") }}</li>
    </ul>
  </ConfirmDialog>
</template>

<style scoped>
.freeze-dialog__list {
  margin: 0;
  padding-inline-start: var(--space-3);
}
</style>
