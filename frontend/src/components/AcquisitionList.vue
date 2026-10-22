<script setup lang="ts">
/**
 * How an entry's file came into the register, each time it came: by upload or from an address,
 * when, under what name the server answered, and by which addresses a fetch got there.
 */
import type { Acquisition } from "@/api";
import { LOCALE, messages, t } from "@/i18n/de";
import { isWebAddress } from "@/readableAddress";
import { word } from "@/registerWords";

defineProps<{ acquisitions: Acquisition[] }>();

const dateTime = new Intl.DateTimeFormat(LOCALE, { dateStyle: "medium", timeStyle: "short" });
</script>

<template>
  <ul class="acquisitions">
    <li v-for="(acquisition, index) in acquisitions" :key="index" class="card acquisition">
      <dl class="facts">
        <dt>{{ t("entryPage.acquisitions.method") }}</dt>
        <dd>{{ word(messages.entryPage.acquisitionMethod, acquisition.method) }}</dd>
        <dt>{{ t("entryPage.acquisitions.acquiredAt") }}</dt>
        <dd>
          <time :datetime="acquisition.acquired_at">{{ dateTime.format(new Date(acquisition.acquired_at)) }}</time>
        </dd>
        <template v-if="acquisition.received_name">
          <dt>{{ t("entryPage.acquisitions.receivedName") }}</dt>
          <dd><bdi>{{ acquisition.received_name }}</bdi></dd>
        </template>
        <template v-if="acquisition.chain.length">
          <dt>{{ t("entryPage.acquisitions.chain") }}</dt>
          <dd>
            <ol class="acquisition__chain">
              <li v-for="(address, step) in acquisition.chain" :key="step">
                <a v-if="isWebAddress(address)" class="facts__address" :href="address" rel="noreferrer">
                  <bdi>{{ address }}</bdi>
                </a>
                <bdi v-else class="facts__address">{{ address }}</bdi>
              </li>
            </ol>
          </dd>
        </template>
      </dl>
    </li>
  </ul>
</template>

<style scoped>
.acquisitions {
  display: grid;
  gap: var(--space-1);
  margin: 0;
  padding: 0;
  list-style: none;
}

.acquisition {
  margin: 0;
}

.acquisition__chain {
  margin: 0;
  padding-inline-start: var(--space-3);
}
</style>
