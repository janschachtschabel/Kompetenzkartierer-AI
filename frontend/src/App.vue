<script setup lang="ts">
/**
 * The shell: the way past it for the keyboard, the product's name, the
 * navigation an account's roles open, who is signed in and the way out - or,
 * for a visitor, the way in. The routed page renders in the one main region.
 */
import { computed, onMounted, onUnmounted } from "vue";
import { RouterLink, RouterView, useRoute, useRouter } from "vue-router";

import { clearToken, getToken } from "@/api";
import AppIcon from "@/components/AppIcon.vue";
import BrandMark from "@/components/BrandMark.vue";
import { keepFocusInPage } from "@/focusRescue";
import { LOCALE, t } from "@/i18n/de";
import { visibleDestinations, type Destination } from "@/navigation";
import { clearSession, ensureSession, session, sessionState } from "@/session";

const route = useRoute();
const router = useRouter();

const destinations = computed(() => (session.value ? visibleDestinations(session.value.roles) : []));
const roles = computed(() =>
  new Intl.ListFormat(LOCALE).format((session.value?.roles ?? []).map((role) => t(`app.roles.${role}`))),
);

/**
 * Where the navigation says the reader is: on the destination's own page, or on a page that lies
 * within it (route meta `section`) - an entry's page in the register's. Said for every
 * destination, so the router link's own "page" on its exact match agrees with it.
 */
function current(destination: Destination): "page" | "true" | undefined {
  if (route.name === destination.name) return "page";
  return route.meta.section === destination.name ? "true" : undefined;
}

let stopFocusRescue: (() => void) | null = null;

onMounted(() => {
  void ensureSession();
  stopFocusRescue = keepFocusInPage(() => document.getElementById("main"));
});

onUnmounted(() => stopFocusRescue?.());

/** Only here: the token is gone from this tab; the server keeps it until an admin revokes it. */
async function signOut(): Promise<void> {
  clearToken();
  clearSession();
  await router.push({ name: "login" });
}
</script>

<template>
  <a href="#main" class="skip-link">{{ t("app.skipToContent") }}</a>
  <header class="shell">
    <RouterLink class="shell__brand" :to="{ name: 'start' }">
      <BrandMark :size="28" />
      <span class="shell__wordmark">{{ t("app.title") }}</span>
    </RouterLink>
    <nav v-if="session" class="shell__nav" :aria-label="t('app.nav.label')">
      <ul class="shell__destinations">
        <li v-for="destination in destinations" :key="destination.name">
          <RouterLink class="shell__destination" :to="{ name: destination.name }" :aria-current="current(destination)">
            <AppIcon :name="destination.icon" />
            {{ t(destination.label) }}
          </RouterLink>
        </li>
      </ul>
    </nav>
    <div class="shell__account">
      <p v-if="session" class="shell__who">
        {{ t("app.signedInAs") }} <strong>{{ session.name }}</strong>
        <span class="shell__roles">{{ t("app.roleList", { roles }) }}</span>
      </p>
      <!-- The way out - for a token held whose account did not load too: a
           refused token behind a locked address has no other -->
      <button
        v-if="session || sessionState === 'failed'"
        type="button"
        class="btn secondary btn-sm shell__sign-out"
        @click="signOut"
      >
        {{ t("app.signOut") }}
      </button>
      <!-- Not while a token is held and its account loads: that is no visitor -->
      <RouterLink
        v-else-if="route.name !== 'login' && !getToken()"
        class="btn primary btn-sm"
        :to="{ name: 'login' }"
      >
        {{ t("app.signIn") }}
      </RouterLink>
    </div>
  </header>
  <!-- `tabindex="-1"` so the skip link and a navigation can put focus here; it
       keeps the region out of the tab order itself. -->
  <main id="main" tabindex="-1">
    <RouterView />
  </main>
</template>

<style scoped>
.skip-link {
  position: absolute;
  top: var(--space-1);
  left: var(--space-1);
  z-index: 10;
  padding: var(--space-1) var(--space-2);
  background: var(--surface);
  color: var(--text);
  border: 1px solid var(--control-border);
  border-radius: var(--radius);
  box-shadow: var(--shadow-2);
  /* Out of sight until focused, never `display: none`: that would take it out
     of the tab order, which is the one thing it exists for. */
  transform: translateY(-200%);
  transition: transform var(--dur-1) var(--ease);
}

.skip-link:focus-visible {
  transform: translateY(0);
}

/* The main region takes focus as a target - of the skip link, after a
   navigation - so a screen reader starts reading there; it is no control, and
   a focus ring around it framed the whole page. Its first control shows the
   ring again on the next Tab. */
#main:focus-visible {
  outline: none;
}

.shell {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-1) var(--space-3);
  padding: var(--space-1) var(--space-3);
  background: var(--surface);
  border-bottom: 1px solid var(--border);
}

.shell__brand {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  min-height: 44px;
  color: var(--text);
  font-weight: 700;
  letter-spacing: var(--tracking-tight);
  text-decoration: none;
}

.shell__nav {
  flex: 1 1 auto;
}

.shell__destinations {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-1);
  margin: 0;
  padding: 0;
  list-style: none;
}

.shell__destination {
  display: inline-flex;
  align-items: center;
  gap: var(--space-0);
  min-height: 44px;
  padding: 0 var(--space-1);
  border-radius: var(--radius);
  color: var(--text);
  text-decoration: none;
}

/* Where you are - the page, or the section it lies in: a wash and a weight, not a colour
   alone. Drawn by the state the link says, so the eye sees what a screen reader hears. */
.shell__destination[aria-current] {
  background: var(--accent-wash);
  font-weight: 600;
}

.shell__account {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-1) var(--space-2);
  margin-inline-start: auto;
}

.shell__who {
  margin: 0;
  font-size: var(--step--1);
}

.shell__roles {
  display: block;
  color: var(--text-muted);
}
</style>
