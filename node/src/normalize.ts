/**
 * Message normalization. SPEC.md section 5.8.
 *
 * Strips the parts of a message that vary between occurrences of the same bug,
 * so that "User 4821 not found" and "User 9173 not found" fingerprint
 * identically.
 *
 * The rule order here is normative and must match every other port exactly;
 * `conformance/normalize.json` is what keeps it honest.
 */

export const MAX_LENGTH = 200;

const QUOTED = /'[^']*'|"[^"]*"/g;
const EMAIL = /[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/g;
const URL = /\b[A-Za-z][A-Za-z0-9+.-]*:\/\/\S+/g;
const UUID = /\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b/gi;
const HEX_PREFIXED = /\b0x[0-9a-f]+\b/gi;
// A hex run only counts as an identifier when it mixes digits and a-f letters;
// requiring both keeps English words like "effaced" out of the placeholder.
const HEX_RUN = /\b(?=[0-9a-f]*[a-f])(?=[0-9a-f]*[0-9])[0-9a-f]{7,}\b/gi;
const WIN_PATH = /[A-Za-z]:\\[^\s'"]+/g;
const UNIX_PATH = /\/[A-Za-z0-9._-]+(?:\/[A-Za-z0-9._-]+)+/g;
const IPV6 = /\[[0-9a-f]*:[0-9a-f:]*\]/gi;
const IPV4 = /\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b/g;
const NUMBER = /[-+]?\d+(?:\.\d+)?/g;
const WHITESPACE = /\s+/g;

/** Reduce `message` to its invariant shape. */
export function normalizeMessage(message: string): string {
  if (!message) return "";
  let text = message;
  text = text.replace(QUOTED, "<s>");
  text = text.replace(EMAIL, "<email>");
  text = text.replace(URL, "<url>");
  text = text.replace(UUID, "<id>");
  text = text.replace(HEX_PREFIXED, "<hash>");
  text = text.replace(HEX_RUN, "<hash>");
  text = text.replace(WIN_PATH, "<path>");
  text = text.replace(UNIX_PATH, "<path>");
  text = text.replace(IPV6, "<ip>");
  text = text.replace(IPV4, "<ip>");
  text = text.replace(NUMBER, "<n>");
  text = text.replace(WHITESPACE, " ").trim();
  return text.toLowerCase().slice(0, MAX_LENGTH);
}
