import { describe, expect, it } from "vitest";

import { readableAddress } from "@/readableAddress";

describe("an address as a reader tells it from another", () => {
  it("keeps the host and the whole path, where candidates of one title differ", () => {
    expect(readableAddress("https://www.lehrplanplus.bayern.de/fachlehrplan/realschule/10/biologie")).toBe(
      "www.lehrplanplus.bayern.de/fachlehrplan/realschule/10/biologie",
    );
  });

  it("keeps the query, which tells a portal's pages apart", () => {
    expect(readableAddress("http://example.org/inhalt?fach=mathematik&jgs=7")).toBe("example.org/inhalt?fach=mathematik&jgs=7");
  });

  it("decodes the escapes, and drops what tells nothing apart: the scheme, a closing slash, the fragment", () => {
    expect(readableAddress("https://example.org/Lehrpl%C3%A4ne/Bio%20logie.pdf#seite=2")).toBe("example.org/Lehrpläne/Bio logie.pdf");
    expect(readableAddress("https://example.org/physik/")).toBe("example.org/physik");
    expect(readableAddress("https://example.org/")).toBe("example.org");
  });

  it("keeps an escape that decodes to nothing readable as it is", () => {
    expect(readableAddress("https://example.org/plan%E0%A4%A.pdf")).toBe("example.org/plan%E0%A4%A.pdf");
    // a sign that turns the text around would make one address look like another
    expect(readableAddress("https://example.org/plan%E2%80%AEfdp.exe")).toBe("example.org/plan%E2%80%AEfdp.exe");
  });

  it("leaves what is no web address as it is", () => {
    expect(readableAddress("javascript:alert(1)")).toBe("javascript:alert(1)");
    expect(readableAddress("keine Adresse")).toBe("keine Adresse");
  });
});
