/** Blare's own error types. */

export class BlareError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "BlareError";
  }
}

/**
 * An invalid configuration value.
 *
 * Deliberately fatal: an alerting library that starts up quietly with a
 * misread setting is indistinguishable from one that works, and you find out
 * during the incident it was supposed to tell you about.
 */
export class ConfigError extends BlareError {
  constructor(message: string) {
    super(message);
    this.name = "ConfigError";
  }
}
