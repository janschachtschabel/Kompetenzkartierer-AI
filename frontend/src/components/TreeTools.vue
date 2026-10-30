<script setup lang="ts">
/**
 * The tools of a document's tree (plan M1 9.8, Paket 9c2c M6, M8; treeCheck.ts): a node added at its top, by its
 * owner while it is open (`create-top`), and the tree checked again - X5 once more, no model asked - by its owner
 * or an editor. Started, the page reads the tree again (`changed`: closed now, a job open) and the job is followed
 * here (JobProgress), its button kept and busy until it has ended, so the keyboard stays where it pressed; ended,
 * the tree is read again and the button offered beside how it went. An editor who does not own the document may
 * not follow the job - it runs in the owner's account -: where it is gone from them that is said, with a way to
 * read the tree again, until the tree comes back no longer closed by a job. A refusal is said by its code at the
 * button, another failure as one; neither reads the tree again.
 */
import { computed, nextTick, ref, watch } from "vue";

import { CHECK_KIND, type Tree } from "@/api";
import AppIcon from "@/components/AppIcon.vue";
import JobProgress from "@/components/JobProgress.vue";
import NoticeText from "@/components/NoticeText.vue";
import { jobLabel } from "@/documentJobs";
import { focusIsFree } from "@/focusRescue";
import { t } from "@/i18n/de";
import type { JobGone } from "@/jobWatch";
import type { Notice } from "@/notice";
import { refusalText } from "@/refusals";
import { startTreeCheck } from "@/treeCheck";

const props = defineProps<{ tree: Tree; documentId: string }>();
const emit = defineEmits<{ "create-top": []; changed: [] }>();

const starting = ref(false);
// the job a start gave back, shown until another start; open while it waits or runs
const followed = ref<string | null>(null);
const running = ref(false);
// the job is the owner's alone: the tree tells when the check is done
const lost = ref(false);
const problem = ref<Notice | null>(null);
const checkButton = ref<HTMLElement | null>(null);
const readButton = ref<HTMLElement | null>(null);

const busy = computed(() => starting.value || running.value);
// whoever may edit the tree - its owner, an editor - may check it (an editor who may review may edit too)
const offered = computed(() => props.tree.editable || busy.value);

async function check(): Promise<void> {
  if (busy.value) return; // the button stays focusable while busy, so it can be pressed again
  starting.value = true;
  problem.value = null;
  const done = await startTreeCheck(props.documentId);
  starting.value = false;
  if (done.outcome === "started") {
    followed.value = done.jobId;
    running.value = true;
    lost.value = false; // a refusal leaves it: the check it tells of still runs
    emit("changed");
  } else if (done.outcome === "refused") {
    problem.value = { text: refusalText(done.code) ?? t("documents.tree.check.failed") };
  } else {
    problem.value = done.problem;
  }
}

// Busy until the tree read again says how it stands: the button does not go and come back meanwhile
let ended = false;

function onEnded(): void {
  ended = true;
  emit("changed");
}

watch(
  () => props.tree,
  () => {
    if (ended) running.value = ended = false;
  },
);

// The button went with the job where the tree is closed: the keyboard left on nothing goes to reading it again
async function onGone(why: JobGone): Promise<void> {
  running.value = false;
  if (why !== "not_found") return; // JobProgress says why it may follow no more
  followed.value = null;
  lost.value = true;
  await nextTick();
  if (focusIsFree()) readButton.value?.focus();
}

// The tree read again no longer closed by a job: the check is done, the note and its button go with it
watch(
  () => props.tree.closed,
  async (closed) => {
    if (!lost.value || closed === "job_open") return;
    lost.value = false;
    await nextTick();
    if (focusIsFree()) checkButton.value?.focus();
  },
);
</script>

<template>
  <div class="tree-tools">
    <p v-if="offered" class="tree-tools__buttons">
      <button v-if="tree.editable" type="button" class="btn btn-sm secondary" @click="emit('create-top')">
        {{ t("documents.tree.create.node") }}
      </button>
      <!-- aria-disabled, not disabled: a disabled button drops the focus it holds -->
      <button
        v-if="offered"
        ref="checkButton"
        type="button"
        class="btn btn-sm secondary"
        :aria-disabled="busy || undefined"
        @click="check"
      >
        {{ t("documents.tree.check.button") }}
      </button>
    </p>
    <p v-if="problem" class="field__error tree-tools__problem" role="alert">
      <AppIcon name="warning" /> <NoticeText :notice="problem" />
    </p>
    <JobProgress
      v-if="followed"
      :key="followed"
      :job-id="followed"
      :label="jobLabel(CHECK_KIND)"
      @ended="onEnded"
      @gone="onGone"
    />
    <div v-if="lost" class="tree-tools__lost">
      <p class="tree-tools__note">{{ t("documents.tree.check.lost") }}</p>
      <button ref="readButton" type="button" class="btn btn-sm secondary" @click="emit('changed')">
        {{ t("documents.tree.check.readAgain") }}
      </button>
    </div>
    <!-- always in the page, so a screen reader hears the note when it comes -->
    <p class="visually-hidden" role="status">{{ lost ? t("documents.tree.check.lost") : "" }}</p>
  </div>
</template>

<style scoped>
/* Its parts are cells of the tree's section: with nothing offered it takes no room, its gap not standing twice;
   the status line, out of the flow, none at all. */
.tree-tools {
  display: contents;
}

.tree-tools__buttons {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-1);
  margin: 0;
}

.tree-tools__problem,
.tree-tools__note {
  margin: 0;
}

.tree-tools__note {
  max-width: var(--reading-width);
  color: var(--text-muted);
}

.tree-tools__lost {
  display: grid;
  justify-items: start;
  gap: var(--space-1);
}
</style>
