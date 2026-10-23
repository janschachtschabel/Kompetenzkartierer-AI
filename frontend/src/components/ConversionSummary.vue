<script setup lang="ts">
/**
 * A conversion done: how many pages it read, with which tool and when, what it noticed in the
 * text - signs a symbol font left unmapped, a text layer that looks damaged - and the way to its
 * blocks. The findings are what to check before quoting from the blocks.
 */
import { computed } from "vue";
import { RouterLink } from "vue-router";

import type { Conversion } from "@/api";
import AppIcon from "@/components/AppIcon.vue";
import { findingText } from "@/conversionWords";
import { momentFormat, t } from "@/i18n/de";

const props = defineProps<{ conversion: Conversion; sourceId: string }>();

const findings = computed(() => props.conversion.findings.map(findingText));
</script>

<template>
  <div class="summary">
    <dl class="facts">
      <dt>{{ t("conversions.facts.pages") }}</dt>
      <dd>{{ conversion.pages }}</dd>
      <dt>{{ t("conversions.facts.engine") }}</dt>
      <dd>{{ conversion.engine }} {{ conversion.engine_version }}</dd>
      <template v-if="conversion.finished_at">
        <dt>{{ t("conversions.facts.finishedAt") }}</dt>
        <dd>
          <time :datetime="conversion.finished_at">{{ momentFormat.format(new Date(conversion.finished_at)) }}</time>
        </dd>
      </template>
    </dl>
    <h3 class="summary__heading">{{ t("conversions.findingsHeading") }}</h3>
    <ul v-if="findings.length" class="summary__findings" data-test="findings">
      <li v-for="(text, index) in findings" :key="index" class="summary__finding"><AppIcon name="warning" /> {{ text }}</li>
    </ul>
    <p v-else class="summary__none">{{ t("conversions.noFindings") }}</p>
    <RouterLink class="btn secondary" :to="{ name: 'conversion', params: { id: sourceId } }">
      {{ t("conversions.showBlocks") }}
    </RouterLink>
  </div>
</template>

<style scoped>
.summary {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: var(--space-1);
}

.summary .facts {
  align-self: stretch;
}

.summary__heading {
  margin: var(--space-1) 0 0;
}

.summary__findings {
  display: grid;
  gap: var(--space-0);
  max-width: var(--reading-width);
  margin: 0;
  padding: 0;
  list-style: none;
}

/* The sign repeats what the words say: a finding is something to check. */
.summary__finding {
  display: flex;
  gap: var(--space-1);
}

.summary__none {
  margin: 0;
  color: var(--text-muted);
}
</style>
