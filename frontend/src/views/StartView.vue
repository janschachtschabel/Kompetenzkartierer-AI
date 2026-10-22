<script setup lang="ts">
/**
 * The start: an account is greeted; a visitor learns what the service is and
 * what PUBLIC_ACCESS opens without an account, and finds the sign-in.
 */
import { onMounted, ref } from "vue";
import { RouterLink } from "vue-router";

import { getInfo, getToken, type Info } from "@/api";
import ErrorState from "@/components/ErrorState.vue";
import LoadingState from "@/components/LoadingState.vue";
import { t } from "@/i18n/de";
import { failureNotice, type Notice } from "@/notice";
import { ensureSession, session, sessionFailure } from "@/session";

const info = ref<Info | null>(null);
const failure = ref<Notice | null>(null);
const loading = ref(true);

async function load(): Promise<void> {
  loading.value = true;
  failure.value = null;
  try {
    // an account's own start needs no word about visitors
    await ensureSession();
    if (session.value) return;
    if (getToken()) {
      // a token is held and its account did not load: that is no visitor
      failure.value = failureNotice(sessionFailure.value, t("start.accountFailed"), {
        // a good token never meets the address's lock (app/api/deps.py): this one was refused
        tooManyRequests: () => t("start.accountRejected"),
      });
      return;
    }
    info.value = await getInfo();
  } catch (error) {
    failure.value = failureNotice(error, t("start.infoFailed"));
  } finally {
    loading.value = false;
  }
}

onMounted(load);
</script>

<template>
  <div class="page start">
    <template v-if="session">
      <h1>{{ t("start.welcome", { name: session.name }) }}</h1>
      <p class="start__lead">{{ t("start.intro") }}</p>
    </template>
    <template v-else>
      <h1>{{ t("app.title") }}</h1>
      <LoadingState v-if="loading" />
      <ErrorState
        v-else-if="failure"
        :message="failure.text"
        :reason="failure.reason"
        :explanation="failure.explanation"
        @retry="load"
      />
      <template v-else-if="info">
        <p class="start__lead">{{ t("start.about") }}</p>
        <p v-if="info.public_access === 'off'">{{ t("start.visitor.off") }}</p>
        <p v-else class="page-notice start__open">{{ t(`start.visitor.${info.public_access}`) }}</p>
        <p>
          <RouterLink class="btn primary" :to="{ name: 'login' }">{{ t("start.signIn") }}</RouterLink>
        </p>
      </template>
    </template>
  </div>
</template>

<style scoped>
/* The reading width on the text, not on the page: the page keeps the frame every page has. */
.start p {
  max-width: var(--reading-width);
}

.start__lead {
  font-size: var(--step-1);
  color: var(--text-muted);
  margin: 0 0 var(--space-3);
}

.start__open {
  margin: 0 0 var(--space-2);
}
</style>
