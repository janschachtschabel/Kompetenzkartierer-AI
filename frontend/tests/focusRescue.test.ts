import { flushPromises } from "@vue/test-utils";
import { afterEach, describe, expect, it } from "vitest";

import { focusById, focusIsFree, keepFocusInPage } from "@/focusRescue";

/**
 * The keyboard's place survives the removal of what had focus (old app, audit
 * 2026-09-26, E-104). A confirmed deletion returned focus to the row's delete
 * button, the reload then took the row away, and focus fell to <body>: the
 * next Tab started again at the top of the page.
 */
describe("keepFocusInPage", () => {
  let stop: (() => void) | null = null;

  afterEach(() => {
    stop?.();
    stop = null;
    document.body.innerHTML = "";
  });

  function page(): { main: HTMLElement; doomed: HTMLElement; other: HTMLElement } {
    document.body.innerHTML =
      '<main id="main" tabindex="-1"><ul><li><button id="doomed">x</button></li></ul>' +
      '<button id="other">y</button></main>';
    return {
      main: document.getElementById("main") as HTMLElement,
      doomed: document.getElementById("doomed") as HTMLElement,
      other: document.getElementById("other") as HTMLElement,
    };
  }

  const settle = () => flushPromises();

  it("moves focus to the fallback when the focused element is taken out of the page", async () => {
    const { main, doomed } = page();
    stop = keepFocusInPage(() => main);
    doomed.focus();

    (doomed.closest("li") as HTMLElement).remove();
    await settle();

    expect(document.activeElement).toBe(main);
  });

  it("leaves focus alone when it had moved on before the removal", async () => {
    const { main, doomed, other } = page();
    stop = keepFocusInPage(() => main);
    doomed.focus();
    other.focus();

    (doomed.closest("li") as HTMLElement).remove();
    await settle();

    expect(document.activeElement).toBe(other);
  });

  it("keeps the keyboard inside an open modal instead of sending it behind the scrim", async () => {
    // A share taken back in the share dialog lost its row, and focus went to
    // <main> behind the scrim, out of reach of Escape and the Tab trap (old app, audit
    // 2026-10-01, G-44). Any modal's first control is a better place.
    document.body.innerHTML =
      '<main id="main" tabindex="-1"><div role="dialog" aria-modal="true">' +
      '<button id="close">x</button><ul><li><button id="doomed">y</button></li></ul></div></main>';
    const main = document.getElementById("main") as HTMLElement;
    const doomed = document.getElementById("doomed") as HTMLElement;
    stop = keepFocusInPage(() => main);
    doomed.focus();

    (doomed.closest("li") as HTMLElement).remove();
    await settle();

    expect(document.activeElement).toBe(document.getElementById("close"));
  });

  // A focused button that becomes disabled loses focus as well: Chromium fires
  // focusout and leaves focus on <body> (old app, audit 2026-10-01, 7.9-7). The button
  // stays in the page, so no removal is there to notice. jsdom applies no such
  // focus fixup -- a disabled button keeps focus there -- and ignores blur() on
  // a disabled element, so blur() comes first here: the observer runs after
  // both and finds what the browser leaves, a disabled button and <body>.
  it("moves focus to the fallback when the focused button is disabled", async () => {
    const { main, doomed } = page();
    stop = keepFocusInPage(() => main);
    doomed.focus();

    doomed.blur();
    (doomed as HTMLButtonElement).disabled = true;
    await settle();

    expect(document.activeElement).toBe(main);
  });

  it("does so too where the browser has not moved focus off it yet", async () => {
    // Whether focus has left by the time the observer runs is the engine's
    // business; a disabled button has lost it either way.
    const { main, doomed } = page();
    stop = keepFocusInPage(() => main);
    doomed.focus();

    (doomed as HTMLButtonElement).disabled = true;
    await settle();

    expect(document.activeElement).toBe(main);
  });

  it("keeps the keyboard inside an open modal when its focused button is disabled", async () => {
    // Publishing in the share dialog disabled its button, and focus fell
    // behind the scrim, out of reach for Escape and the Tab trap.
    document.body.innerHTML =
      '<main id="main" tabindex="-1"><div role="dialog" aria-modal="true">' +
      '<button id="close">x</button><button id="doomed">y</button></div></main>';
    const main = document.getElementById("main") as HTMLElement;
    const doomed = document.getElementById("doomed") as HTMLButtonElement;
    stop = keepFocusInPage(() => main);
    doomed.focus();

    doomed.blur();
    doomed.disabled = true;
    await settle();

    expect(document.activeElement).toBe(document.getElementById("close"));
  });

  it("does nothing once stopped", async () => {
    const { main, doomed } = page();
    stop = keepFocusInPage(() => main);
    stop();
    stop = null;
    doomed.focus();

    (doomed.closest("li") as HTMLElement).remove();
    await settle();

    expect(document.activeElement).not.toBe(main);
  });
});

/** The keyboard sent to a place named by its id: a step's link, a problem's field, the way to the save. */
describe("focusById", () => {
  afterEach(() => {
    document.body.innerHTML = "";
  });

  it("focuses the element with that id", () => {
    document.body.innerHTML = '<button id="first">a</button><button id="target">b</button>';

    focusById("target");

    expect(document.activeElement?.id).toBe("target");
  });

  it("leaves focus where it was when no element has that id", () => {
    document.body.innerHTML = '<button id="first">a</button>';
    (document.getElementById("first") as HTMLElement).focus();

    focusById("gone");

    expect(document.activeElement?.id).toBe("first");
  });
});

describe("focusIsFree", () => {
  afterEach(() => {
    document.body.innerHTML = "";
  });

  it("is free on <body> and on the main region, where a navigation puts the keyboard", () => {
    document.body.innerHTML = '<main id="main" tabindex="-1"><input id="search"></main>';
    expect(focusIsFree()).toBe(true);

    (document.getElementById("main") as HTMLElement).focus();
    expect(focusIsFree()).toBe(true);
  });

  it("is not free once the person has focused a control", () => {
    document.body.innerHTML = '<main id="main" tabindex="-1"><input id="search"></main>';
    (document.getElementById("search") as HTMLElement).focus();

    expect(focusIsFree()).toBe(false);
  });
});
