<script setup lang="ts">
/**
 * The way through a converted file's pages: the page before, the page after, and any page by
 * its number. At either end the step that leads nowhere says so and keeps the focus; a number
 * the file does not have is refused beside the field. Which page shows is the view's, which
 * keeps it in the address: this only asks for one.
 */
import { ref, watch } from "vue";

import AppIcon from "@/components/AppIcon.vue";
import { t } from "@/i18n/de";
import { sayAnew } from "@/liveRegion";

const props = defineProps<{ page: number; pages: number }>();
const emit = defineEmits<{ go: [page: number] }>();

// v-model makes a number of what the field holds, and leaves a string where it cannot
const typed = ref<string | number>(String(props.page));
const refusal = ref("");

// the field shows the page shown, whichever way it came there
watch(
  () => props.page,
  (page) => {
    typed.value = String(page);
    refusal.value = "";
  },
);

function step(by: number): void {
  const next = props.page + by;
  if (next >= 1 && next <= props.pages) emit("go", next);
}

function jump(): void {
  const wanted = Number(typed.value);
  if (!Number.isInteger(wanted) || wanted < 1 || wanted > props.pages) {
    // the same refusal again is read out again (liveRegion.ts)
    refusal.value = sayAnew(refusal.value, t("conversionPage.pager.invalid", { pages: props.pages }));
    return;
  }
  refusal.value = "";
  if (wanted !== props.page) emit("go", wanted);
}
</script>

<template>
  <div class="pager">
    <nav class="pager__row" :aria-label="t('conversionPage.pager.label')">
      <!-- aria-disabled, not disabled: a disabled button drops the focus it holds, and the last
           press of "Nächste Seite" would send the keyboard to the top of the page -->
      <button
        type="button"
        class="btn secondary btn-sm"
        data-test="previous"
        :aria-disabled="page <= 1 || undefined"
        @click="step(-1)"
      >
        {{ t("conversionPage.pager.previous") }}
      </button>
      <form class="pager__jump" novalidate @submit.prevent="jump">
        <label for="pager-page">{{ t("conversionPage.pager.field") }}</label>
        <input
          id="pager-page"
          v-model="typed"
          class="pager__field"
          type="number"
          inputmode="numeric"
          min="1"
          :max="pages"
          :aria-invalid="refusal ? true : undefined"
          :aria-describedby="refusal ? 'pager-of pager-error' : 'pager-of'"
        />
        <span id="pager-of">{{ t("conversionPage.pager.of", { pages }) }}</span>
        <button type="submit" class="btn secondary btn-sm">{{ t("conversionPage.pager.go") }}</button>
      </form>
      <button
        type="button"
        class="btn secondary btn-sm"
        data-test="next"
        :aria-disabled="page >= pages || undefined"
        @click="step(1)"
      >
        {{ t("conversionPage.pager.next") }}
      </button>
    </nav>
    <p v-if="refusal" id="pager-error" class="field__error" role="alert"><AppIcon name="warning" /> {{ refusal }}</p>
  </div>
</template>

<style scoped>
.pager {
  display: grid;
  gap: var(--space-1);
  margin-block-end: var(--space-3);
}

/* One row where there is room; on a phone the field wraps under the steps. */
.pager__row,
.pager__jump {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-1);
}

/* Wide enough for five digits and the browser's spinner, not the whole row. */
.pager__field {
  inline-size: 6rem;
}
</style>
