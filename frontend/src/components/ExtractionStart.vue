<script setup lang="ts">
/**
 * The start of an extraction from an entry's finished conversion (plan M1 7.5, 7a): a document is
 * made of it, in a sector and for Länder, and its extraction started at once; the page then goes
 * to the document, where the extraction is followed and can be cancelled. The sector is asked
 * for, the entry's own Land chosen already. A refusal - no budget, too many starts - is said
 * below the form, which keeps what was chosen.
 */
import { computed, nextTick, ref } from "vue";
import { useRouter } from "vue-router";

import { makeDocument, type Sector } from "@/api";
import AppIcon from "@/components/AppIcon.vue";
import NoticeText from "@/components/NoticeText.vue";
import { messages, t } from "@/i18n/de";
import { failureNotice, type Notice } from "@/notice";

const props = defineProps<{
  sourceId: string;
  conversionId: string;
  /** The entry's Land as the register has it (ISO 3166-2), chosen at the start. */
  country: string | null;
}>();

const router = useRouter();
const SECTORS = Object.keys(messages.documents.sectors) as Sector[];
const REGIONS = Object.keys(messages.sources.countries);

const sector = ref<Sector | "">("");
const regions = ref<string[]>(props.country && REGIONS.includes(props.country) ? [props.country] : []);
const sectorMissing = ref(false);
const sectorField = ref<HTMLSelectElement | null>(null);
const busy = ref(false);
const failure = ref<Notice | null>(null);

// in the order the list gives them, however they were ticked
const chosenRegions = computed(() => REGIONS.filter((code) => regions.value.includes(code)));

async function onSubmit(): Promise<void> {
  if (busy.value) return; // the button stays focusable while busy, so it can be pressed again
  failure.value = null;
  sectorMissing.value = sector.value === "";
  if (sector.value === "") {
    // the field takes the keyboard: its name, that it is invalid and why are read there
    await nextTick();
    sectorField.value?.focus();
    return;
  }
  busy.value = true;
  try {
    const started = await makeDocument({
      source_id: props.sourceId,
      conversion_id: props.conversionId,
      sector: sector.value,
      regions: chosenRegions.value,
    });
    await router.push({ name: "document", params: { id: started.document.id } });
  } catch (error) {
    failure.value = failureNotice(error, t("documents.start.failed"));
  } finally {
    busy.value = false;
  }
}
</script>

<template>
  <section class="extraction-start" aria-labelledby="extraction-start">
    <h3 id="extraction-start" class="extraction-start__heading">{{ t("documents.start.heading") }}</h3>
    <p class="extraction-start__intro">{{ t("documents.start.intro") }}</p>
    <form novalidate @submit.prevent="onSubmit">
      <div class="field">
        <label for="extraction-sector">{{ t("documents.start.sector") }}</label>
        <select
          id="extraction-sector"
          ref="sectorField"
          v-model="sector"
          :aria-invalid="sectorMissing || undefined"
          :aria-describedby="sectorMissing ? 'extraction-sector-error' : undefined"
          @change="sectorMissing = false"
        >
          <option value="">{{ t("documents.start.sectorChoose") }}</option>
          <option v-for="code in SECTORS" :key="code" :value="code">{{ messages.documents.sectors[code] }}</option>
        </select>
        <p v-if="sectorMissing" id="extraction-sector-error" class="field__error">
          <AppIcon name="warning" /> {{ t("documents.start.sectorMissing") }}
        </p>
      </div>
      <fieldset class="extraction-start__regions" aria-describedby="extraction-regions-hint">
        <legend>{{ t("documents.start.regions") }}</legend>
        <p id="extraction-regions-hint" class="field__hint">{{ t("documents.start.regionsHint") }}</p>
        <div class="extraction-start__boxes">
          <label v-for="code in REGIONS" :key="code" class="extraction-start__box">
            <input v-model="regions" type="checkbox" :value="code" />
            {{ messages.sources.countries[code as keyof typeof messages.sources.countries] }}
          </label>
        </div>
      </fieldset>
      <p v-if="failure" class="field__error" role="alert"><AppIcon name="warning" /> <NoticeText :notice="failure" /></p>
      <!-- aria-disabled, not disabled: a disabled button drops the focus it holds -->
      <button type="submit" class="btn primary" data-test="extraction-start" :aria-disabled="busy || undefined">
        {{ t("documents.start.submit") }}
      </button>
    </form>
  </section>
</template>

<style scoped>
.extraction-start {
  margin-block-start: var(--space-3);
}

.extraction-start__heading {
  margin: 0 0 var(--space-1);
}

.extraction-start__intro {
  max-width: var(--reading-width);
  margin: 0 0 var(--space-2);
}

.extraction-start__regions {
  margin: 0 0 var(--space-2);
  padding: 0;
  border: 0;
}

.extraction-start__regions legend {
  padding: 0;
  font-weight: 600;
}

/* as many columns as fit: at 320px one, a long name wraps within its own */
.extraction-start__boxes {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(min(14rem, 100%), 1fr));
  gap: var(--space-0) var(--space-2);
}

.extraction-start__box {
  display: flex;
  align-items: center;
  gap: var(--space-1);
  min-height: 24px;
}
</style>
