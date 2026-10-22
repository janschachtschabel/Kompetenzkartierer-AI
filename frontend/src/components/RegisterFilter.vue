<script setup lang="ts">
/**
 * What the register shows: the seeds' candidates alone - entries of no account
 * still without their file, which the check looks at - and how far the
 * register has come with an entry. Each change hands on a new value; the page
 * reads the register again with it.
 */
import { computed } from "vue";

import type { RegisterStatus } from "@/api";
import { messages, t } from "@/i18n/de";

export interface RegisterFilters {
  candidates: boolean;
  /** Empty for every status. */
  status: RegisterStatus | "";
}

const model = defineModel<RegisterFilters>({ required: true });

const STATUSES: readonly RegisterStatus[] = ["unchecked", "reachable", "unreachable", "acquired"];

const candidates = computed({
  get: () => model.value.candidates,
  set: (value: boolean) => (model.value = { ...model.value, candidates: value }),
});
const status = computed({
  get: () => model.value.status,
  set: (value: RegisterStatus | "") => (model.value = { ...model.value, status: value }),
});
</script>

<template>
  <fieldset class="register-filter">
    <legend class="register-filter__legend">{{ t("sources.filter.legend") }}</legend>
    <div class="field-grid">
      <div class="field checkbox-field">
        <input
          id="register-candidates"
          v-model="candidates"
          type="checkbox"
          aria-describedby="register-candidates-hint"
        />
        <label for="register-candidates">{{ t("sources.filter.candidates") }}</label>
        <p id="register-candidates-hint" class="field__hint">{{ t("sources.filter.candidatesHint") }}</p>
      </div>
      <div class="field">
        <label for="register-status">{{ t("sources.filter.status") }}</label>
        <select id="register-status" v-model="status" class="form-select">
          <option value="">{{ t("sources.filter.anyStatus") }}</option>
          <option v-for="value in STATUSES" :key="value" :value="value">{{ messages.sources.status[value] }}</option>
        </select>
      </div>
    </div>
  </fieldset>
</template>

<style scoped>
.register-filter {
  margin: 0 0 var(--space-2);
  padding: 0;
  border: 0;
  min-inline-size: 0;
}

.register-filter__legend {
  padding: 0;
  margin-block-end: var(--space-1);
  font-size: var(--step--1);
  font-weight: 600;
}
</style>
