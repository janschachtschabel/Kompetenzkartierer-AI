import { nextTick } from "vue";
import { createRouter, createWebHistory } from "vue-router";

import { getToken, onUnauthorized, type Role } from "@/api";
import { t } from "@/i18n/de";
import { pageTitle } from "@/pageTitle";
import { RETURN_PARAM } from "@/returnTarget";
import { clearSession, ensureSession, hasRole } from "@/session";
import ConversionView from "@/views/ConversionView.vue";
import DocumentTreeView from "@/views/DocumentTreeView.vue";
import DocumentView from "@/views/DocumentView.vue";
import LoginView from "@/views/LoginView.vue";
import SourceDetailView from "@/views/SourceDetailView.vue";
import SourcesView from "@/views/SourcesView.vue";
import StartView from "@/views/StartView.vue";

declare module "vue-router" {
  interface RouteMeta {
    /** The catalogue key of the page's name, for the browser's title. */
    title?: string;
    /** A page only for an account: a visitor goes to the sign-in, with the way back. */
    requiresAuth?: boolean;
    /** A page only for this role: an account without it goes to the start. */
    requiresRole?: Role;
    /** The navigation's destination the page lies within: the navigation marks it as where the reader is. */
    section?: string;
  }
}

export const router = createRouter({
  history: createWebHistory(),
  // A new page opens at its top; back and forward return to where the reader
  // was; a change of the query or the fragment alone is the same page and stays
  // put. A link to the page already open - the same address - goes to its top.
  scrollBehavior: (to, from, saved) =>
    saved ?? (to.path === from.path && to.fullPath !== from.fullPath ? false : { top: 0 }),
  routes: [
    // Open: a visitor sees what PUBLIC_ACCESS opens, an account its start.
    { path: "/", name: "start", component: StartView, meta: { title: "app.titles.start" } },
    { path: "/anmelden", name: "login", component: LoginView, meta: { title: "app.titles.login" } },
    {
      path: "/quellen",
      name: "sources",
      component: SourcesView,
      meta: { title: "app.titles.sources", requiresAuth: true },
    },
    {
      path: "/quellen/:id",
      name: "source",
      component: SourceDetailView,
      props: true,
      // its own name once the entry is loaded (SourceDetailView)
      meta: { title: "app.titles.source", requiresAuth: true, section: "sources" },
    },
    {
      // the page in the query (?seite=3), the first without it (ConversionView)
      path: "/quellen/:id/bloecke",
      name: "conversion",
      component: ConversionView,
      props: true,
      // its own name, the entry's and the page's, once the entry is loaded
      meta: { title: "app.titles.conversion", requiresAuth: true, section: "sources" },
    },
    {
      path: "/dokumente/:id",
      name: "document",
      component: DocumentView,
      props: true,
      // its own name once the document is loaded (DocumentView); it is reached from an entry
      meta: { title: "app.titles.document", requiresAuth: true, section: "sources" },
    },
    {
      // the row chosen and the page of the source in the query (?zeile=node:<id>&seite=3, DocumentTreeView)
      path: "/dokumente/:id/baum",
      name: "documentTree",
      component: DocumentTreeView,
      props: true,
      // its own name once the document is loaded; it is reached from the document's page
      meta: { title: "app.titles.documentTree", requiresAuth: true, section: "sources" },
    },
    { path: "/:rest(.*)*", redirect: { name: "start" } },
  ],
});

router.beforeEach(async (to) => {
  if ((to.meta.requiresAuth || to.meta.requiresRole) && !getToken()) {
    // Where the visitor was going, for the sign-in to send them back to: a
    // bookmark or a shared link would otherwise have to be found again.
    return { name: "login", query: { [RETURN_PARAM]: to.fullPath } };
  }
  if (to.meta.requiresRole) {
    // Loaded here rather than read from the shell: a bookmark runs this before
    // App.vue has mounted, and an empty session would bounce the right account.
    await ensureSession();
    // the token turned out stale: the sign-in, with the way back
    if (!getToken()) return { name: "login", query: { [RETURN_PARAM]: to.fullPath } };
    // without the role, or with no account because its load failed - which
    // the start then says, with a retry
    if (!hasRole(to.meta.requiresRole)) return { name: "start" };
  }
  return true;
});

// Every page names itself (WCAG 2.4.2) and hands focus to its content, so a
// screen reader announces the new page and the next Tab does not walk the
// navigation again. Not on the first load, where focus belongs to the browser;
// not when only the query changes, which is the same page; not where a guard
// held the page.
router.afterEach((to, from, failure) => {
  if (failure) return;
  const key = to.meta.title;
  document.title = pageTitle(typeof key === "string" ? t(key) : undefined);
  if (from.matched.length === 0 || to.path === from.path) return;
  void nextTick(() => document.getElementById("main")?.focus({ preventScroll: true }));
});

// A token the server has stopped accepting: the wrapper drops it, and the next
// place to be is the sign-in, with the page as the way back. The session goes
// with the token, so a later account does not inherit the old name. A refusal
// that arrives once the sign-in is on screen changes nothing.
onUnauthorized(() => {
  clearSession();
  const here = router.currentRoute.value;
  if (here.name === "login") return;
  void router.push({ name: "login", query: here.matched.length ? { [RETURN_PARAM]: here.fullPath } : {} });
});
