import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import { ANCHORS, SRC, scanned, sourceFiles } from "./sources";

/**
 * The rules with legal weight (GDPR; see main.ts on the fonts): no request to a
 * third party from the browser - a CDN link sends every visitor's address -, no
 * personal data in local storage, nothing written to the console, where a
 * token or an input would land in whoever's devtools are open.
 */
const files = [...sourceFiles(SRC, /\.(vue|ts|css)$/), join(process.cwd(), "index.html")];

/** Where the app could keep something past the tab's session, or write it where devtools show it. */
const STORE_OR_CONSOLE = /\blocalStorage\b|\bconsole\.|\bdocument\.cookie\b|\bindexedDB\b|\bcaches\./;

/** URLs that name a namespace, never fetched. */
const NAMESPACES = /^(?:https?:)?\/\/www\.w3\.org\//i;

function withoutComments(source: string): string {
  return source
    .replace(/<!--[\s\S]*?-->/g, "")
    .replace(/\/\*[\s\S]*?\*\//g, "")
    // a line comment, not the "//" of a URL - after a scheme, a quote, `url(` or `=`
    .replace(/(^|[^:"'`(=])\/\/[^\n]*/g, "$1");
}

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
    const offenders = files.flatMap((path) => foreignAddresses(readFileSync(path, "utf8")).map((url) => `${path}: ${url}`));

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
  ])("are recognised: %s", (source) => {
    expect(STORE_OR_CONSOLE.test(withoutComments(source))).toBe(true);
  });

  it("leave the tab's session alone, where the token is kept", () => {
    expect(STORE_OR_CONSOLE.test('sessionStorage.setItem("kka_token", token)')).toBe(false);
  });

  it("hold nothing of the app's but the token in the tab's session", () => {
    const offenders = files.filter((path) => STORE_OR_CONSOLE.test(withoutComments(readFileSync(path, "utf8"))));

    expect(offenders).toEqual([]);
  });
});
