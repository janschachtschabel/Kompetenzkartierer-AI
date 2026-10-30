<script setup lang="ts">
/**
 * What the stages found on a document (plan M1 8b, F8): counted by severity and listed gravest first,
 * each with its severity, what it found in words (findingWords.ts) and the row it is about - as many
 * as the server lists, said where it found more. Read again whenever `refresh` changes (the page bumps
 * it as the extraction moves on), as sectionReading.ts reads. Its owner is offered the repair of the
 * work packages they name (FindingsRepair.vue) while no job of the document waits or runs (`busy`),
 * and only beside findings read since: not while they are read again - the job that just ended may
 * have changed them - nor beside a reading that failed. Once the page follows a repair started
 * here, the button is gone and the keyboard goes to the section's heading, where it was left on
 * nothing.
 */
import { computed, nextTick, onMounted, ref, watch } from "vue";

import { getFindings, type FindingsPage, type Job } from "@/api";
import EmptyState from "@/components/EmptyState.vue";
import ErrorState from "@/components/ErrorState.vue";
import FindingsRepair from "@/components/FindingsRepair.vue";
import LoadingState from "@/components/LoadingState.vue";
import PartialState from "@/components/PartialState.vue";
import { findingText, focusText, SEVERITIES, SEVERITY_TONES } from "@/findingWords";
import { focusIsFree } from "@/focusRescue";
import { t } from "@/i18n/de";
import { useSectionReading } from "@/sectionReading";

const props = defineProps<{ documentId: string; own: boolean; busy: boolean; refresh: number }>();
const emit = defineEmits<{ started: [job: Job] }>();

const heading = ref<HTMLElement | null>(null);
const {
  shown: page,
  failure,
  hidden,
  pending,
  load,
  retry,
} = useSectionReading<FindingsPage>(() => getFindings(props.documentId), t("documents.findings.loadFailed"), heading);
// a repair started here, until the page follows its job
let startedHere = false;

const total = computed(() => SEVERITIES.reduce((sum, severity) => sum + (page.value?.counts[severity] ?? 0), 0));
const rows = computed(() =>
  (page.value?.findings ?? []).map((finding) => ({ finding, said: findingText(finding), about: focusText(finding) })),
);

function onStarted(job: Job): void {
  startedHere = true;
  emit("started", job);
}

watch(
  () => props.busy,
  async (busy) => {
    if (!busy || !startedHere) return;
    startedHere = false;
    await nextTick();
    if (focusIsFree()) heading.value?.focus();
  },
);

onMounted(load);
watch(() => props.refresh, load);
</script>

<template>
  <section aria-labelledby="document-findings">
    <!-- tabindex -1: where the keyboard goes once what it pressed went with its state -->
    <h2 id="document-findings" ref="heading" tabindex="-1">{{ t("documents.findings.heading") }}</h2>
    <template v-if="page === null">
      <!-- no retry: none changes whose content it is -->
      <EmptyState
        v-if="hidden"
        :level="3"
        :title="t('conversionPage.hiddenTitle')"
        :body="t('refusals.file_hidden')"
      />
      <ErrorState
        v-else-if="failure"
        :message="failure.text"
        :reason="failure.reason"
        :explanation="failure.explanation"
        @retry="retry()"
      />
      <LoadingState v-else :label="t('documents.findings.loading')" />
    </template>
    <EmptyState
      v-else-if="!page.findings.length"
      :level="3"
      :title="t('documents.findings.noneTitle')"
      :body="t('documents.findings.noneBody')"
    />
    <template v-else>
      <p class="findings__counts" data-test="findings-counts">
        <template v-for="severity in SEVERITIES" :key="severity">
          <span v-if="page.counts[severity]" class="status-badge" :class="SEVERITY_TONES[severity]">
            {{ t(`documents.findings.counts.${severity}`, { count: page.counts[severity] }) }}
          </span>
        </template>
      </p>
      <p v-if="page.truncated" class="findings__note" data-test="findings-truncated">
        {{ t("documents.findings.truncated", { shown: page.findings.length, total }) }}
      </p>
      <!-- scrolled on its own where wider than a phone, by the keyboard too; a name of its own -->
      <div class="findings" tabindex="0" role="region" :aria-label="t('documents.findings.table')">
        <table>
          <thead>
            <tr>
              <th scope="col">{{ t("documents.findings.columns.severity") }}</th>
              <th scope="col">{{ t("documents.findings.columns.finding") }}</th>
              <th scope="col">{{ t("documents.findings.columns.focus") }}</th>
            </tr>
          </thead>
          <tbody>
            <!-- a finding has no id of its own; the list is read whole each time -->
            <tr v-for="(row, at) in rows" :key="at">
              <td>
                <span class="status-badge" :class="SEVERITY_TONES[row.finding.severity]">
                  {{ t(`documents.findings.severities.${row.finding.severity}`) }}
                </span>
              </td>
              <td class="findings__text">
                <q v-if="row.said.lang" lang="en">{{ row.said.text }}</q>
                <template v-else>{{ row.said.text }}</template>
              </td>
              <td class="findings__text">{{ row.about }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>
    <FindingsRepair
      v-if="own && page"
      :document-id="documentId"
      :repairable="page.repairable"
      :busy="busy || pending || failure !== null"
      @started="onStarted"
    />
    <!-- in the page from the start, so a failure of a later reading is heard -->
    <PartialState :notice="page !== null ? failure : null" :retry="!hidden" @retry="retry()" />
  </section>
</template>

<style scoped>
.findings {
  overflow-x: auto;
}

.findings table {
  border-collapse: collapse;
  min-width: 36rem;
}

.findings th,
.findings td {
  padding: var(--space-0) var(--space-2) var(--space-0) 0;
  text-align: start;
  vertical-align: top;
}

.findings__text {
  overflow-wrap: anywhere;
  max-width: var(--reading-width);
}

.findings__counts {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-1);
  margin: 0 0 var(--space-2);
}

.findings__note {
  max-width: var(--reading-width);
  color: var(--text-muted);
  margin: 0 0 var(--space-2);
}
</style>
