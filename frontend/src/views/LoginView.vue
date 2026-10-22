<script setup lang="ts">
import { ref } from "vue";
import { useRoute, useRouter } from "vue-router";

import { ApiError, checkToken, setToken } from "@/api";
import AppIcon from "@/components/AppIcon.vue";
import { t } from "@/i18n/de";
import { RETURN_PARAM, returnTarget } from "@/returnTarget";
import { setSession } from "@/session";

const router = useRouter();
const route = useRoute();

const token = ref("");
const error = ref("");
const checking = ref(false);

/** Why the token could not be checked. Past too many failures the server answers 429 with the wait. */
function signInFailure(failure: unknown): string {
  if (!(failure instanceof ApiError)) return t("login.errors.server");
  if (failure.kind === "network") return t("login.errors.network");
  if (failure.status !== 429) return t("login.errors.server");
  return failure.retryAfter === undefined
    ? t("login.errors.lockedLater")
    : t("login.errors.locked", { count: Math.max(1, Math.ceil(failure.retryAfter / 60)) });
}

async function onSubmit(): Promise<void> {
  error.value = "";
  const candidate = token.value.trim();
  if (!candidate) {
    error.value = t("login.errors.empty");
    return;
  }

  checking.value = true;
  try {
    const me = await checkToken(candidate);
    if (!me) {
      error.value = t("login.errors.invalid");
      return;
    }
    setToken(candidate);
    // the check answered with the account: the shell needs not ask again
    setSession(me);
    await router.push(returnTarget(route.query[RETURN_PARAM]) ?? { name: "start" });
  } catch (failure) {
    error.value = signInFailure(failure);
  } finally {
    checking.value = false;
  }
}
</script>

<template>
  <!-- A `div`, not a `main`: App.vue renders the page's one main region around
       the router view, and a second one would give the skip link two targets. -->
  <div class="login">
    <section class="login__card card" aria-labelledby="login-heading">
      <h1 id="login-heading" class="login__heading">{{ t("login.heading") }}</h1>
      <p class="login__intro">{{ t("login.intro") }}</p>

      <form class="login__form" novalidate @submit.prevent="onSubmit">
        <div class="field">
          <label for="token">{{ t("login.tokenLabel") }}</label>
          <input
            id="token"
            v-model="token"
            type="password"
            autocomplete="off"
            spellcheck="false"
            :aria-invalid="error ? true : undefined"
            :aria-describedby="error ? 'login-error' : undefined"
          />
        </div>

        <p v-if="error" id="login-error" class="login__error" role="alert">
          <AppIcon name="warning" /> {{ error }}
        </p>

        <button type="submit" class="btn primary login__submit" :disabled="checking">
          {{ checking ? t("login.checking") : t("login.submit") }}
        </button>
      </form>
    </section>
  </div>
</template>

<style scoped>
/* Centred in what is left of the viewport rather than pinned to a corner: the
   form is four lines long. */
.login {
  display: grid;
  place-items: center;
  min-height: 70vh;
  padding: var(--space-3);
}

.login__card {
  inline-size: 100%;
  max-inline-size: 26rem;
  margin: 0;
  padding: var(--space-3);
  box-shadow: var(--shadow-1);
}

.login__heading {
  font-size: var(--step-2);
}

.login__intro {
  margin: 0 0 var(--space-3);
  color: var(--text-muted);
  font-size: var(--step--1);
}

.login__form {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.login__submit {
  /* The one action on the page: the full width of the card. */
  inline-size: 100%;
  min-height: 44px;
}

/* The icon repeats what the words say; neither is carried by colour alone. */
.login__error {
  display: flex;
  align-items: center;
  gap: var(--space-1);
  margin: 0;
  color: var(--danger);
  font-size: var(--step--1);
}
</style>
