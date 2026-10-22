import { t } from "@/i18n/de";

/**
 * What the browser's title bar, its tabs and bookmarks call a page (WCAG 2.4.2),
 * and what a screen reader announces on arrival: its name, then the app's.
 */
export function pageTitle(name?: string): string {
  return name ? `${name} · ${t("app.title")}` : t("app.title");
}
