/**
 * Redaction. SPEC.md section 6.
 *
 * Blare posts failure data into a chat room, so the library carries the burden
 * of not leaking secrets rather than trusting each caller to remember.
 * Redaction runs after fingerprinting (so it can never destabilise grouping)
 * and before rendering (so no sink ever sees a raw value).
 */

export const PLACEHOLDER = "[redacted]";
export const MAX_DEPTH = 8;

/** Section 6.1, compared against keys with separators and case removed. */
export const SECRET_KEYS = new Set([
  "password", "passwd", "pwd", "secret", "token", "apikey", "accesskey",
  "secretkey", "privatekey", "clientsecret", "authorization", "auth",
  "cookie", "setcookie", "session", "sessionid", "csrf", "xsrf",
  "creditcard", "cardnumber", "cvv", "ssn", "otp", "passphrase",
  "refreshtoken", "accesstoken", "idtoken", "signature", "salt",
  "encryptionkey",
]);

const NON_ALNUM = /[^a-z0-9]/g;

const PRIVATE_KEY = /-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----/g;
const JWT = /\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+/g;
const BEARER = /\b(Bearer)\s+[A-Za-z0-9._~+/=-]+/gi;
const AWS_KEY = /\b(?:AKIA|ASIA)[A-Z0-9]{16}\b/g;
const SLACK_TOKEN = /\bxox[baprs]-[A-Za-z0-9-]+/g;
const GITHUB_TOKEN = /\bgh[pousr]_[A-Za-z0-9]{36,}\b/g;
const URL_CREDENTIALS = /\b([A-Za-z][A-Za-z0-9+.-]*:\/\/)[^\s:/@]+:[^\s/@]+@/g;
const DIGIT_RUN = /\b\d{13,19}\b/g;

function normalizeKey(key: string): string {
  return String(key).toLowerCase().replace(NON_ALNUM, "");
}

function luhn(digits: string): boolean {
  let total = 0;
  let alternate = false;
  for (let i = digits.length - 1; i >= 0; i -= 1) {
    let value = digits.charCodeAt(i) - 48;
    if (alternate) {
      value *= 2;
      if (value > 9) value -= 9;
    }
    total += value;
    alternate = !alternate;
  }
  return total % 10 === 0;
}

/** Applies section 6 to text and to nested structures. */
export class Redactor {
  private readonly extra: RegExp[];

  constructor(extraPatterns: readonly string[] = []) {
    this.extra = extraPatterns
      .filter(Boolean)
      .map((pattern) => new RegExp(pattern, "g"));
  }

  text(value: string): string {
    if (!value) return value;
    let out = value.replace(PRIVATE_KEY, "[redacted-private-key]");
    out = out.replace(JWT, "[redacted-jwt]");
    out = out.replace(BEARER, (_m, keyword: string) => `${keyword} ${PLACEHOLDER}`);
    out = out.replace(AWS_KEY, "[redacted-aws-key]");
    out = out.replace(SLACK_TOKEN, "[redacted-slack-token]");
    out = out.replace(GITHUB_TOKEN, "[redacted-github-token]");
    out = out.replace(URL_CREDENTIALS, (_m, scheme: string) => `${scheme}${PLACEHOLDER}@`);
    out = out.replace(DIGIT_RUN, (run) => (luhn(run) ? "[redacted-card]" : run));
    for (const pattern of this.extra) out = out.replace(pattern, PLACEHOLDER);
    return out;
  }

  /** Redact a structure: secret keys by name, every string by pattern. */
  value(input: unknown, depth = 0): unknown {
    if (depth > MAX_DEPTH) return input;
    if (typeof input === "string") return this.text(input);
    if (Array.isArray(input)) return input.map((item) => this.value(item, depth + 1));
    if (input && typeof input === "object") {
      const out: Record<string, unknown> = {};
      for (const [key, item] of Object.entries(input as Record<string, unknown>)) {
        out[key] = SECRET_KEYS.has(normalizeKey(key))
          ? PLACEHOLDER
          : this.value(item, depth + 1);
      }
      return out;
    }
    return input;
  }
}
