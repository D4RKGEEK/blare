/**
 * The Blare client.
 *
 * Pipeline for every captured failure, in this order:
 *
 *     classify → fingerprint → decide → redact → render → deliver
 *
 * Fingerprinting happens *before* redaction so that changing a redaction rule
 * can never regroup history, and redaction happens before rendering so that no
 * sink can ever see a raw secret.
 */

import { Config, type ConfigInput } from "./config.js";
import { Candidate, Decider, type Decision } from "./decide.js";
import { buildTitle, toPayload, type EventInput, type Payload,
  type RequestContext } from "./event.js";
import * as fp from "./fingerprint.js";
import { Redactor } from "./redact.js";
import { buildSinks, ConsoleSink, type Sink } from "./sinks/index.js";
import { buildStore, type Store } from "./state.js";
import { SyncTransport, Transport } from "./transport.js";

export interface CaptureOptions {
  level?: string;
  logger?: string;
  extra?: Record<string, unknown>;
  request?: RequestContext | null;
}

export interface MessageOptions extends CaptureOptions {
  typeName?: string;
  location?: fp.Location;
  stack?: string[];
}

export interface ClientOptions extends ConfigInput {
  sinks?: string[];
  sinkObjects?: Sink[];
  synchronous?: boolean;
  clock?: () => number;
  /** Where Blare's own diagnostics go. Never the capture path. */
  onWarning?: (message: string) => void;
}

/** The fully-qualified name of a thrown value, so two `ValidationError`s stay distinct. */
function typeNameOf(error: unknown): string {
  if (error instanceof Error) {
    const named = error as Error & { code?: string };
    if (error.name && error.name !== "Error") return error.name;
    if (named.code) return `Error.${named.code}`;
    return error.constructor?.name || "Error";
  }
  return typeof error;
}

function messageOf(error: unknown): string {
  if (error instanceof Error) return error.message;
  if (typeof error === "string") return error;
  try {
    return JSON.stringify(error) ?? String(error);
  } catch {
    return String(error);
  }
}

export class Blare {
  readonly config: Config;
  readonly sinks: Sink[];
  private readonly clock: () => number;
  private readonly redactor: Redactor;
  private readonly store: Store;
  private readonly decider: Decider;
  private readonly transport: Transport;
  private readonly warn: (message: string) => void;
  private busy = false;
  private installedHooks: Array<() => void> = [];

  suppressed = 0;
  droppedByIgnore = 0;

  constructor(options: ClientOptions = {}) {
    const { sinkObjects, synchronous, clock, onWarning, ...configInput } = options;
    this.warn = onWarning ?? ((message: string) => process.stderr.write(`${message}\n`));
    this.config = configInput instanceof Config ? configInput : Config.fromEnv(configInput);
    this.clock = clock ?? (() => Date.now() / 1000);
    this.redactor = new Redactor(this.config.redact);

    this.store = buildStore(this.config.state, this.config.service, this.warn);
    this.decider = new Decider(this.store, {
      dedupeWindow: this.config.dedupeWindow,
      maxPerHour: this.config.maxPerHour,
      ignore: this.config.ignore,
      resolveAfter: this.config.resolveAfter,
    });

    let resolvedSinks = sinkObjects ?? buildSinks(this.config.sinks, this.config.timeout);
    if (this.config.dryRun && !sinkObjects) {
      this.warn("blare: BLARE_DRY_RUN is set; alerts go to stderr only");
      resolvedSinks = [new ConsoleSink()];
    }
    for (const sink of resolvedSinks) sink.onWarning = this.warn;
    this.sinks = resolvedSinks;

    const TransportClass = synchronous ? SyncTransport : Transport;
    this.transport = new TransportClass(resolvedSinks, this.config.timeout);
    this.transport.onWarning = this.warn;

    if (!this.config.enabled) {
      this.warn("blare: disabled by BLARE_ENABLED");
    } else if (this.config.sinks.length === 0 && !sinkObjects) {
      this.warn(
        "blare: no sinks configured, so nothing will be sent. " +
          "Set BLARE_SINKS to your webhook URL.",
      );
    }
  }

  // -- capture ---------------------------------------------------------

  /** Report a thrown value. Returns true if an alert was queued. */
  captureException(error: unknown, options: CaptureOptions = {}): boolean {
    if (error === undefined || error === null) return false;
    const { location, stack } = fp.locationFromError(error);
    return this.process({
      kind: "exception",
      typeName: typeNameOf(error),
      message: messageOf(error),
      level: options.level ?? "error",
      logger: options.logger ?? "",
      location,
      stack,
      extra: options.extra,
      request: options.request ?? null,
    });
  }

  /** Report a failure that is not a thrown value. */
  captureMessage(message: string, options: MessageOptions = {}): boolean {
    return this.process({
      kind: "log",
      typeName: options.typeName || options.logger || "message",
      message,
      level: options.level ?? "error",
      logger: options.logger ?? "",
      location: options.location ?? { ...fp.EMPTY_LOCATION },
      stack: options.stack ?? [],
      extra: options.extra,
      request: options.request ?? null,
    });
  }

  // -- pipeline --------------------------------------------------------

  private process(input: {
    kind: string; typeName: string; message: string; level: string; logger: string;
    location: fp.Location; stack: string[];
    extra?: Record<string, unknown>; request: RequestContext | null;
  }): boolean {
    if (!this.config.active) return false;
    // Blare's own failures are reported through `warn`, and that must not come
    // back in as an event whose delivery fails and warns again.
    if (this.busy) return false;
    this.busy = true;
    try {
      return this.processInner(input);
    } catch (error) {
      // Capture is instrumentation. If instrumentation breaks, the
      // application still has to work.
      this.warn(`blare: capture failed: ${String(error)}`);
      return false;
    } finally {
      this.busy = false;
    }
  }

  private processInner(input: {
    kind: string; typeName: string; message: string; level: string; logger: string;
    location: fp.Location; stack: string[];
    extra?: Record<string, unknown>; request: RequestContext | null;
  }): boolean {
    const now = this.clock();
    const fingerprint = fp.compute(
      input.kind, input.typeName, fp.locationKey(input.location), input.message,
    );
    const candidate: Candidate = {
      fingerprint,
      typeName: input.typeName,
      title: buildTitle(input.typeName, input.message),
      logger: input.logger,
    };

    const outcome = this.decider.evaluate(candidate, now);
    if (outcome.decision === null) {
      this.droppedByIgnore += 1;
      return false;
    }

    for (const [resolvedFingerprint, notice] of outcome.resolved) {
      this.emit({
        fingerprint: resolvedFingerprint,
        kind: input.kind,
        level: "info",
        typeName: input.typeName,
        message: "",
        service: this.config.service,
        environment: this.config.environment,
        host: this.config.host,
        timestamp: now,
        state: notice.state,
        total: notice.total,
        firstSeen: notice.firstSeen,
        windowSeconds: this.config.dedupeWindow,
      });
    }

    const decision: Decision = outcome.decision;
    if (!decision.send) {
      this.suppressed += 1;
      return false;
    }

    return this.emit({
      fingerprint,
      kind: input.kind,
      level: input.level,
      typeName: input.typeName,
      message: input.message,
      service: this.config.service,
      environment: this.config.environment,
      host: this.config.host,
      timestamp: now,
      state: decision.state,
      logger: input.logger,
      file: input.location.file,
      function: input.location.function,
      line: input.location.line,
      stack: input.stack.slice(0, this.config.stackFrames),
      request: input.request,
      extra: input.extra ?? {},
      sinceLastAlert: decision.sinceLastAlert,
      total: decision.total,
      firstSeen: decision.firstSeen,
      windowSeconds: this.config.dedupeWindow,
      rateLimited: decision.rateLimited,
    });
  }

  private emit(event: EventInput): boolean {
    const payload = this.redactor.value(toPayload(event)) as Payload;
    return this.transport.submit(payload);
  }

  // -- lifecycle -------------------------------------------------------

  /**
   * Alert on a crash, then let the process die as it would have.
   *
   * Node gives no second chance here: after `uncaughtException` the process is
   * in an undefined state, so Blare flushes what it can and re-raises rather
   * than pretending the application can carry on.
   */
  installProcessHooks(): void {
    const onUncaught = (error: Error) => {
      this.captureException(error, { level: "critical" });
      void this.flush().finally(() => {
        // Restore the default behaviour and re-throw, so the process still
        // dies with the original error and the original exit code.
        process.removeListener("uncaughtException", onUncaught);
        throw error;
      });
    };
    const onRejection = (reason: unknown) => {
      this.captureException(reason, { level: "error" });
    };
    process.on("uncaughtException", onUncaught);
    process.on("unhandledRejection", onRejection);
    this.installedHooks.push(() => {
      process.removeListener("uncaughtException", onUncaught);
      process.removeListener("unhandledRejection", onRejection);
    });
  }

  /** Wait for queued alerts to be delivered. */
  flush(timeoutMs?: number): Promise<boolean> {
    return this.transport.flush(timeoutMs);
  }

  /** Flush, detach the hooks, and release the store. */
  async close(timeoutMs?: number): Promise<void> {
    for (const remove of this.installedHooks) remove();
    this.installedHooks = [];
    await this.transport.close(timeoutMs);
    this.store.close();
  }

  /**
   * Send one synthetic alert to each sink and report the outcome.
   *
   * "Is this wired up?" should be answerable on a quiet afternoon rather than
   * discovered during the outage it was installed for.
   */
  async selftest(): Promise<Array<[string, boolean]>> {
    const payload = this.redactor.value(toPayload({
      fingerprint: "selftest00000000",
      kind: "log",
      level: "error",
      typeName: "blare.SelfTest",
      message: "Blare is connected. This is a test alert.",
      service: this.config.service,
      environment: this.config.environment,
      host: this.config.host,
      timestamp: this.clock(),
      state: "new",
      logger: "blare",
      file: "blare/client.ts",
      function: "selftest",
      line: 0,
      windowSeconds: this.config.dedupeWindow,
    })) as Payload;

    const results: Array<[string, boolean]> = [];
    for (const sink of this.sinks) {
      let ok = false;
      try {
        ok = await sink.send(payload);
      } catch (error) {
        this.warn(`blare: selftest on ${sink.redactedUrl()} raised: ${String(error)}`);
      }
      results.push([sink.redactedUrl(), ok]);
    }
    return results;
  }

  /** Counters for the host's own monitoring and tests. */
  stats(): Record<string, number> {
    return {
      delivered: this.transport.delivered,
      failed: this.transport.failed,
      droppedByQueue: this.transport.dropped,
      suppressed: this.suppressed,
      droppedByIgnore: this.droppedByIgnore,
    };
  }
}
