<script setup lang="ts">
/**
 * The documents made of a register entry's conversion (plan M1 7a), on the entry's page: each
 * with how its latest extraction stands, and the way to its page, where the extraction is
 * followed, cancelled or started again.
 */
import { onMounted, ref } from "vue";
import { RouterLink } from "vue-router";

import { listDocuments, type CurriculumDocument } from "@/api";
import ErrorState from "@/components/ErrorState.vue";
import LoadingState from "@/components/LoadingState.vue";
import { lastStatus } from "@/documentJobs";
import { momentFormat, t } from "@/i18n/de";
import { failureNotice, type Notice } from "@/notice";

const props = defineProps<{ sourceId: string }>();

const documents = ref<CurriculumDocument[] | null>(null);
const failure = ref<Notice | null>(null);

async function load(): Promise<void> {
  failure.value = null;
  try {
    documents.value = await listDocuments(props.sourceId);
  } catch (error) {
    failure.value = failureNotice(error, t("documents.list.loadFailed"));
  }
}

function moment(value: string): string {
  return momentFormat.format(new Date(value));
}

onMounted(load);
</script>

<template>
  <section class="documents" aria-labelledby="source-documents">
    <h2 id="source-documents">{{ t("documents.list.heading") }}</h2>
    <ErrorState
      v-if="failure"
      :message="failure.text"
      :reason="failure.reason"
      :explanation="failure.explanation"
      @retry="load()"
    />
    <LoadingState v-else-if="documents === null" />
    <p v-else-if="documents.length === 0" class="documents__note">{{ t("documents.list.empty") }}</p>
    <ul v-else class="documents__list">
      <li v-for="item in documents" :key="item.id" class="documents__item">
        <RouterLink :to="{ name: 'document', params: { id: item.id } }">
          <!-- one untitled is told from another by when it was made, in the link's name too -->
          <bdi>{{ item.title || t("documents.list.untitled", { made: moment(item.created_at) }) }}</bdi>
        </RouterLink>
        <span class="documents__meta">
          <!-- an untitled one has its time in its name already -->
          <template v-if="item.title">
            <time :datetime="item.created_at">{{ moment(item.created_at) }}</time>
            ·
          </template>
          {{ item.extraction ? lastStatus(item.extraction) : t("documents.page.none") }}
        </span>
      </li>
    </ul>
  </section>
</template>

<style scoped>
.documents__note {
  max-width: var(--reading-width);
  color: var(--text-muted);
  margin: 0;
}

.documents__list {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  margin: 0;
  padding: 0;
  list-style: none;
}

.documents__item {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-0) var(--space-2);
  overflow-wrap: anywhere;
}

.documents__meta {
  color: var(--text-muted);
  font-size: var(--step--1);
}
</style>
