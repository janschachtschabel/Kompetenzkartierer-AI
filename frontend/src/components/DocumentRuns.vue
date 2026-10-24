<script setup lang="ts">
/**
 * The runs of a document's stages, in the order they began (plan M1 7a): each with its attempt,
 * how it stands and why it failed - in the page's words where it knows them, else as the server
 * wrote it, quoted as English and shortened.
 */
import type { Run } from "@/api";
import { messages, momentFormat, t } from "@/i18n/de";
import { JOB_FAILURE_CODES, jobFailureText } from "@/jobMessages";
import { word } from "@/registerWords";

defineProps<{ runs: Run[] }>();

/** The most of a server's sentence the table shows; the rest is cut at a word. */
const MOST_SIGNS = 200;
const JOB_CODES: ReadonlySet<string> = new Set(JOB_FAILURE_CODES);

function stageName(stage: string): string {
  return word(messages.documents.stages, stage);
}

function moment(value: string): string {
  return momentFormat.format(new Date(value));
}

/** A known reason in German; otherwise null, and the server's words are quoted. */
function knownReason(failure: string): string | null {
  if (Object.hasOwn(messages.documents.runFailures, failure)) return t(`documents.runFailures.${failure}`);
  return JOB_CODES.has(failure) ? jobFailureText(failure) : null;
}

function shortened(failure: string): string {
  if (failure.length <= MOST_SIGNS) return failure;
  const cut = failure.slice(0, MOST_SIGNS);
  const space = cut.lastIndexOf(" ");
  return `${space > MOST_SIGNS / 2 ? cut.slice(0, space) : cut}…`;
}
</script>

<template>
  <section aria-labelledby="document-runs">
    <h2 id="document-runs">{{ t("documents.page.runs") }}</h2>
    <!-- wider than a phone: scrolled on its own, by the keyboard too; a name of its own, as two
         regions of one name would be one landmark twice -->
    <div v-if="runs.length" class="runs" tabindex="0" role="region" :aria-label="t('documents.page.runsTable')">
      <table>
        <thead>
          <tr>
            <th scope="col">{{ t("documents.page.columns.stage") }}</th>
            <th scope="col">{{ t("documents.page.columns.attempt") }}</th>
            <th scope="col">{{ t("documents.page.columns.state") }}</th>
            <th scope="col">{{ t("documents.page.columns.started") }}</th>
            <th scope="col">{{ t("documents.page.columns.finished") }}</th>
            <th scope="col">{{ t("documents.page.columns.failure") }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(run, index) in runs" :key="index">
            <td>{{ stageName(run.stage) }}</td>
            <td>{{ run.attempt ?? "–" }}</td>
            <td>{{ word(messages.documents.runStates, run.state) }}</td>
            <td><time :datetime="run.started_at">{{ moment(run.started_at) }}</time></td>
            <td>
              <time v-if="run.finished_at" :datetime="run.finished_at">{{ moment(run.finished_at) }}</time>
              <template v-else>–</template>
            </td>
            <td>
              <template v-if="run.failure">
                <template v-if="knownReason(run.failure)">{{ knownReason(run.failure) }}</template>
                <q v-else lang="en">{{ shortened(run.failure) }}</q>
              </template>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <p v-else class="runs__note">{{ t("documents.page.noRuns") }}</p>
  </section>
</template>

<style scoped>
.runs {
  overflow-x: auto;
}

.runs table {
  border-collapse: collapse;
  min-width: 36rem;
}

.runs th,
.runs td {
  padding: var(--space-0) var(--space-2) var(--space-0) 0;
  text-align: start;
  vertical-align: top;
}

.runs q {
  overflow-wrap: anywhere;
}

.runs__note {
  max-width: var(--reading-width);
  color: var(--text-muted);
  margin: 0 0 var(--space-2);
}
</style>
