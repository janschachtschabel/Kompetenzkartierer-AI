import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import { ANCHORS, SRC, inCatalogue, scanned, sourceFiles, withoutComments } from "./sources";

/**
 * The rules with legal weight (GDPR; see main.ts on the fonts): no request to a
 * third party from the browser - a CDN link sends every visitor's address -, no
 * personal data in local storage, nothing written to the console, where a
 * token or an input would land in whoever's devtools are open.
 */
const files = [...sourceFiles(SRC, /\.(vue|ts|css)$/), join(process.cwd(), "index.html")];

/** Where the app could keep something past the tab's session, or write it where devtools show it. */
const STORE_OR_CONSOLE =
  /\blocalStorage\b|\bconsole\s*(?:\.|\[)|\bdocument\.cookie\b|\bcookieStore\b|\bindexedDB\b|\bcaches\.(?:open|match)\(/;

/** URLs that name a namespace, never fetched: the W3C's, and the curriculum vocabularies' (cv:, the profiles'). */
const NAMESPACES = /^(?:https?:)?\/\/(?:www\.w3\.org|w3id\.org\/wlo)\//i;

/** The addresses `source` would fetch from elsewhere: with a scheme or protocol-relative, in any case. */
function foreignAddresses(source: string): string[] {
  // a link fetches nothing until someone follows it
  const fetching = withoutComments(source).replace(/<a\b(?:[^>"]|"[^"]*")*>/gi, "");
  return [...fetching.matchAll(/(?:https?:)?\/\/[a-z0-9-]+(?:\.[a-z0-9-]+)+[^\s"'`)<>]*/gi)]
    .map(([address]) => address)
    .filter((address) => !NAMESPACES.test(address));
}

it("scans the sources and the page's head", () => {
  scanned(files, ...ANCHORS, "style.css", "index.html");
});

describe("a third party", () => {
  it("is recognised in a script, a stylesheet or a link, not in a comment or a namespace", () => {
    expect(foreignAddresses('<link href="https://fonts.googleapis.com/css2?family=Roboto">')).toHaveLength(1);
    expect(foreignAddresses('@import url("https://cdn.example.org/x.css");')).toHaveLength(1);
    expect(foreignAddresses("// see https://example.org/why")).toEqual([]);
    expect(foreignAddresses('<svg xmlns="http://www.w3.org/2000/svg">')).toEqual([]);
    expect(foreignAddresses('const CV = "https://w3id.org/wlo/curriculum/vocab#";')).toEqual([]);
    expect(foreignAddresses('fetch("https://w3id.org/other/x")')).toHaveLength(1); // only the curriculum's
  });

  it.each([
    // protocol-relative, as copied CDN snippets write it
    '<script src="//cdn.example.org/a.js"></script>',
    '<img src="//tracker.example.org/p.gif">',
    "@import url(//fonts.googleapis.com/css2?family=Roboto);",
    '<link href="HTTPS://fonts.example.org/x.css">',
  ])("is recognised however the address is written: %s", (source) => {
    expect(foreignAddresses(source)).toHaveLength(1);
  });

  it("is not a link someone follows: it fetches nothing until they do", () => {
    expect(foreignAddresses('<a href="https://www.kmk.org/themen.html" target="_blank" rel="noopener">')).toEqual([]);
  });

  it("is asked for nothing at all", () => {
    // the catalogue's words are shown, never fetched: an address in a sentence is no request
    const fetching = files.filter((path) => !inCatalogue(path));
    scanned(fetching, ...ANCHORS, "style.css", "index.html");
    const offenders = fetching.flatMap((path) =>
      foreignAddresses(readFileSync(path, "utf8")).map((url) => `${path}: ${url}`),
    );

    expect(offenders).toEqual([]);
  });
});

describe("the browser's own stores and console", () => {
  it.each([
    'localStorage.setItem("kka_token", token)',
    "console.log(input)",
    'document.cookie = "kka_token=" + token',
    'indexedDB.open("kka")',
    'caches.open("kka")',
    'cookieStore.set("kka_token", token)',
    'console["log"](input)',
  ])("are recognised: %s", (source) => {
    expect(STORE_OR_CONSOLE.test(withoutComments(source))).toBe(true);
  });

  it.each([
    'sessionStorage.setItem("kka_token", token)',
    // a map of the page's own, named like the browser's store
    "const caches = new Map(); caches.get(key); caches.has(key);",
  ])("leave alone what is no store: %s", (source) => {
    expect(STORE_OR_CONSOLE.test(source)).toBe(false);
  });

  it("hold nothing of the app's but the token in the tab's session", () => {
    const offenders = files.filter((path) => STORE_OR_CONSOLE.test(withoutComments(readFileSync(path, "utf8"))));

    expect(offenders).toEqual([]);
  });
});
