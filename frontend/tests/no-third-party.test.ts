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

/** URLs that name a namespace, never fetched. */
const NAMESPACES = /^https?:\/\/www\.w3\.org\//;

function withoutComments(source: string): string {
  return source
    .replace(/<!--[\s\S]*?-->/g, "")
    .replace(/\/\*[\s\S]*?\*\//g, "")
    // a line comment, not the "//" of a URL
    .replace(/(^|[^:"'`])\/\/[^\n]*/g, "$1");
}

/** The addresses `source` would fetch from elsewhere. */
function foreignAddresses(source: string): string[] {
  return [...withoutComments(source).matchAll(/https?:\/\/[^\s"'`)<>]+/g)]
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

  it("is asked for nothing at all", () => {
    const offenders = files.flatMap((path) => foreignAddresses(readFileSync(path, "utf8")).map((url) => `${path}: ${url}`));

    expect(offenders).toEqual([]);
  });
});

describe("the browser's own stores and console", () => {
  it("hold nothing of the app's but the token in the tab's session", () => {
    const offenders = files.filter((path) => /\blocalStorage\b|\bconsole\./.test(withoutComments(readFileSync(path, "utf8"))));

    expect(offenders).toEqual([]);
  });
});
