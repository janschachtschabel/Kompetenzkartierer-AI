<script setup lang="ts">
/**
 * The form of a row to add (plan M1 9.8, Paket 9c2b L4, L10; rowCreate.ts): the sector's fields, for a statement
 * its anchors - chosen in the source, coming by `addAnchor` - and the button that adds it. Added, it gives the
 * new row's key; a field's problem takes the keyboard to the field or the anchors' list; where the tree closed
 * it says why and keeps the draft; where the row it goes under is gone it says so to the panel. Cancelled with
 * entries it asks first. It tells the panel whether a draft is open (the leave guard), none once it is gone.
 */
import { computed, nextTick, onBeforeUnmount, ref, watch } from "vue";

import { ANCHORS, heldAnchors } from "@/anchorDraft";
import type { Form } from "@/api";
import AnchorDraftList from "@/components/AnchorDraftList.vue";
import AppIcon from "@/components/AppIcon.vue";
import ConfirmDialog from "@/components/ConfirmDialog.vue";
import NoticeText from "@/components/NoticeText.vue";
import RowForm from "@/components/RowForm.vue";
import type { RowKey } from "@/documentTree";
import { t } from "@/i18n/de";
import { refusalText } from "@/refusals";
import { useRowCreate, type CreateTarget } from "@/rowCreate";

const props = defineProps<{ target: CreateTarget; form: Form }>();
const emit = defineEmits<{ created: [key: RowKey]; closed: [code: string]; gone: []; cancel: []; dirty: [open: boolean] }>();

const creating = useRowCreate(props.target, props.form);
const { fields, draft, saving, errors, problem, closed, dirty } = creating;
const formRef = ref<InstanceType<typeof RowForm> | null>(null);
const anchorList = ref<InstanceType<typeof AnchorDraftList> | null>(null);
const closedNotice = ref<HTMLElement | null>(null);
const asking = ref(false);

// a statement's anchors as its draft holds them; a node's draft holds none
const anchors = computed(() => heldAnchors(draft.value));

watch(dirty, (open) => emit("dirty", open), { immediate: true });
onBeforeUnmount(() => emit("dirty", false));

async function submit(): Promise<void> {
  const done = await creating.save();
  await nextTick();
  if (done.outcome === "created") emit("created", done.key);
  else if (done.outcome === "invalid") {
    const first = Object.keys(errors.value)[0];
    if (first === ANCHORS) anchorList.value?.focus();
    else if (first) formRef.value?.focusField(first);
  } else if (done.outcome === "closed" && closed.value) {
    closedNotice.value?.focus();
    emit("closed", closed.value);
  } else if (done.outcome === "gone") emit("gone");
}

function cancel(): void {
  if (dirty.value) asking.value = true;
  else emit("cancel");
}

function discard(): void {
  asking.value = false;
  emit("cancel");
}

/** Take an anchor chosen in the source into a statement's draft. */
function addAnchor(code: string): void {
  creating.addAnchor(code);
}

defineExpose({ addAnchor });
</script>

<template>
  <div class="row-creator">
    <!-- tabindex -1: where the keyboard goes once the tree closed on the draft -->
    <p v-if="closed" ref="closedNotice" class="field__error row-creator__closed" role="alert" tabindex="-1">
      <AppIcon name="warning" /> {{ refusalText(closed) }}
    </p>
    <p v-if="problem" class="field__error row-creator__problem" role="alert">
      <AppIcon name="warning" /> <NoticeText :notice="problem" />
    </p>
    <RowForm
      ref="formRef"
      v-model="draft"
      :fields="fields"
      :errors="errors"
      :saving="saving"
      :save-label="t('documents.tree.create.save')"
      @submit="submit"
    >
      <AnchorDraftList
        v-if="anchors"
        ref="anchorList"
        :codes="anchors"
        :error="errors[ANCHORS] ?? null"
        @remove="creating.removeAnchor"
      />
    </RowForm>
    <p class="row-creator__cancel">
      <button type="button" class="btn secondary" @click="cancel">{{ t("documents.tree.create.cancel") }}</button>
    </p>
    <ConfirmDialog
      v-if="asking"
      :title="t('documents.tree.create.discard.title')"
      :message="t('documents.tree.create.discard.message')"
      :confirm-label="t('documents.tree.create.discard.confirm')"
      :cancel-label="t('documents.tree.create.discard.cancel')"
      @confirm="discard"
      @cancel="asking = false"
    />
  </div>
</template>

<style scoped>
.row-creator {
  display: grid;
  gap: var(--space-1);
}

.row-creator p {
  margin: 0;
}
</style>
