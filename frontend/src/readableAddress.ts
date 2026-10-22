// An address as a reader tells it from another. The seed's candidates often share their title -
// land, subject, school form - and many of their addresses share host and last part too
// (…/realschule/5/biologie, …/realschule/6/biologie): what tells them apart is the whole path
// and the query. Left out is only what tells none apart: the scheme, a closing slash, the fragment.

/** A sign that is no visible text: a control, or a format sign such as one that turns the text around. */
const INVISIBLE = /[\p{Cc}\p{Cf}]/u;

/** `text` with its escapes decoded where they decode to visible text; else as it is. */
function decoded(text: string): string {
  try {
    const plain = decodeURIComponent(text);
    return INVISIBLE.test(plain) ? text : plain;
  } catch {
    return text; // an escape that is none: "%E0%A4%A"
  }
}

/** Only an address of the web becomes a link: whatever else came is shown as it is. */
export function isWebAddress(address: string | null): address is string {
  return address !== null && /^https?:\/\//i.test(address);
}

/** `address` without what tells no address from another; what is no web address, as it is. */
export function readableAddress(address: string): string {
  let url: URL;
  try {
    url = new URL(address);
  } catch {
    return address;
  }
  if (url.protocol !== "https:" && url.protocol !== "http:") return address;
  const path = url.pathname.replace(/\/$/, "");
  return url.host + decoded(path + url.search);
}
