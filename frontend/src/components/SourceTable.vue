<script setup lang="ts">
/**
 * The register's entries as a table: what each is, where it comes from, how
 * far the register has come with it and on what terms it may be used - and how
 * many of all there are it shows, with the way to the next page.
 */
import { nextTick, ref } from "vue";

import type { RegisterStatus, SourceEntry } from "@/api";
import { LOCALE, messages, t } from "@/i18n/de";

defineProps<{ entries: SourceEntry[]; total: number; loadingMore?: boolean }>();
defineEmits<{ more: [] }>();

const body = ref<HTMLTableSectionElement | null>(null);

/**
 * Hands the focus to the row at `index` once it is drawn: after "Weitere laden"
 * the first new entry, where reading goes on - the button may have gone, and
 * with it the focus, which would otherwise fall back to the page's top.
 */
async function focusRow(index: number): Promise<void> {
  await nextTick();
  // the body's own rows: refs in a v-for keep no order
  body.value?.rows[index]?.focus();
}

defineExpose({ focusRow });

/** The words for a register value; the value itself where the page has none yet (tests/registerLabels.test.ts). */
function word(words: Readonly<Record<string, string>>, value: string): string {
  return words[value] ?? value;
}

// The pill by what the state means (style.css, .status-badge); the word in it carries the meaning
const TONE: Record<RegisterStatus, string> = {
  unchecked: "neutral",
  reachable: "warning",
  unreachable: "error",
  acquired: "success",
};

const dateFormat = new Intl.DateTimeFormat(LOCALE, { dateStyle: "medium" });
</script>

<template>
  <div class="register">
    <!-- Focusable and named: on a narrow screen the table scrolls sideways, and a
         keyboard can only scroll what it can reach -->
    <div class="register__scroll" tabindex="0" role="region" :aria-label="t('sources.register.scrollLabel')">
      <table class="register__table">
        <caption class="visually-hidden">{{ t("sources.register.heading") }}</caption>
        <thead>
          <tr>
            <th scope="col">{{ t("sources.register.columns.title") }}</th>
            <th scope="col">{{ t("sources.register.columns.provenance") }}</th>
            <th scope="col">{{ t("sources.register.columns.status") }}</th>
            <th scope="col">{{ t("sources.register.columns.rights") }}</th>
            <th scope="col">{{ t("sources.register.columns.added") }}</th>
          </tr>
        </thead>
        <tbody ref="body">
          <!-- tabindex -1: a target for focusRow, outside the tab order -->
          <tr v-for="entry in entries" :key="entry.id" tabindex="-1">
            <td>
              <!-- an import is titled by its file's name, once the fetch has the file -->
              <bdi class="register__title">{{ entry.title || entry.url }}</bdi>
              <span class="register__aside">
                <bdi v-if="entry.file">{{ entry.file.name }}</bdi>
                <template v-else>{{ t("sources.register.noFile") }}</template>
              </span>
            </td>
            <td>
              {{ word(messages.sources.provenance, entry.provenance) }}
              <span v-if="entry.mine" class="register__aside">{{ t("sources.register.mine") }}</span>
            </td>
            <td>
              <span class="status-badge" :class="TONE[entry.register_status]">
                {{ word(messages.sources.status, entry.register_status) }}
              </span>
            </td>
            <td>{{ word(messages.sources.rights, entry.rights_status) }}</td>
            <td>
              <time :datetime="entry.created_at">{{ dateFormat.format(new Date(entry.created_at)) }}</time>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <div class="register__foot">
      <!-- a status: "Weitere laden" is heard to have worked -->
      <p class="register__count" role="status">{{ t("sources.register.shown", { shown: entries.length, total }) }}</p>
      <!-- aria-disabled, not disabled: a disabled button drops the focus it holds -->
      <button
        v-if="entries.length < total"
        data-test="more"
        type="button"
        class="btn secondary btn-sm"
        :aria-disabled="loadingMore || undefined"
        @click="$emit('more')"
      >
        {{ t("sources.register.more") }}
      </button>
    </div>
  </div>
</template>

<style scoped>
.register__scroll {
  overflow-x: auto;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--surface);
}

.register__scroll:focus-visible {
  outline: 3px solid var(--focus);
  outline-offset: 2px;
}

.register__table {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--step--1);
}

.register__table th,
.register__table td {
  padding: var(--space-1) var(--space-2);
  text-align: start;
  vertical-align: top;
  border-bottom: 1px solid var(--border);
}

.register__table th {
  font-weight: 600;
  white-space: nowrap;
  background: var(--surface-subtle);
}

.register__table tbody tr:last-child td {
  border-bottom: 0;
}

/* A row takes focus only from focusRow; it shows where reading goes on. */
.register__table tbody tr:focus-visible {
  outline: 3px solid var(--focus);
  outline-offset: -3px;
}

/* The title gets the room; a long one breaks rather than widening every other column. */
.register__title {
  display: block;
  min-inline-size: 12rem;
  font-weight: 500;
  overflow-wrap: anywhere;
}

.register__aside {
  display: block;
  color: var(--text-muted);
  font-size: var(--step--2);
  overflow-wrap: anywhere;
}

.register__foot {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-1) var(--space-2);
  margin-block-start: var(--space-1);
}

.register__count {
  margin: 0;
  color: var(--text-muted);
  font-size: var(--step--1);
}
</style>
