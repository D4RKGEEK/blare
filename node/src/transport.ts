/**
 * Delivery. SPEC.md section 3.2.
 *
 * Alerts leave through a bounded queue drained by a single async loop. Both
 * halves matter: a chat webhook sitting on a 5 second timeout must not add 5
 * seconds to a production request, and a chat outage must not turn into
 * unbounded memory growth. When the queue is full Blare drops alerts and
 * counts the drops, because dropping an alert is survivable and stalling the
 * application is not.
 */

import type { Payload } from "./event.js";
import type { Sink } from "./sinks/index.js";

export const QUEUE_SIZE = 100;

export class Transport {
  protected readonly sinks: Sink[];
  protected readonly timeout: number;
  private readonly queue: Payload[] = [];
  private draining: Promise<void> | null = null;
  private closed = false;
  onWarning?: (message: string) => void;

  dropped = 0;
  delivered = 0;
  failed = 0;

  constructor(sinks: readonly Sink[], timeout = 5) {
    this.sinks = [...sinks];
    this.timeout = timeout;
  }

  /** Queue one event. Returns false if it was dropped. */
  submit(payload: Payload): boolean {
    if (this.closed) return false;
    if (this.queue.length >= QUEUE_SIZE) {
      this.dropped += 1;
      this.onWarning?.(
        `blare: delivery queue full; dropped an alert (${this.dropped} dropped in total)`,
      );
      return false;
    }
    this.queue.push(payload);
    if (!this.draining) this.draining = this.drain();
    return true;
  }

  private async drain(): Promise<void> {
    try {
      while (this.queue.length > 0) {
        const payload = this.queue.shift() as Payload;
        await this.deliver(payload);
      }
    } finally {
      this.draining = null;
      // A submit that landed while the last await was pending must not be
      // left sitting in the queue with nobody draining it.
      if (this.queue.length > 0) this.draining = this.drain();
    }
  }

  protected async deliver(payload: Payload): Promise<void> {
    // Each sink is independent: a dead Discord webhook must not stop the
    // Slack alert that someone is actually watching.
    for (const sink of this.sinks) {
      try {
        if (await sink.send(payload)) this.delivered += 1;
        else this.failed += 1;
      } catch (error) {
        this.failed += 1;
        this.onWarning?.(`blare: sink ${sink.redactedUrl()} raised: ${String(error)}`);
      }
    }
  }

  /** Wait for the queue to drain. True if it emptied in time. */
  async flush(timeoutMs?: number): Promise<boolean> {
    const deadline = Date.now() + (timeoutMs ?? this.timeout * 1000);
    while ((this.draining || this.queue.length > 0) && Date.now() < deadline) {
      await (this.draining ?? new Promise<void>((done) => setTimeout(done, 5)));
      if (this.queue.length === 0 && !this.draining) break;
    }
    return this.queue.length === 0 && !this.draining;
  }

  /** Flush within the deadline, then refuse further work. */
  async close(timeoutMs?: number): Promise<void> {
    if (this.closed) return;
    await this.flush(timeoutMs);
    this.closed = true;
  }
}

/**
 * Delivers immediately and awaits the result.
 *
 * Used by the self-test and by host test suites, where "did it actually go
 * out?" has to be answerable before the call returns.
 */
export class SyncTransport extends Transport {
  private pending: Promise<void> = Promise.resolve();

  override submit(payload: Payload): boolean {
    this.pending = this.pending.then(() => this.deliver(payload));
    return true;
  }

  override async flush(): Promise<boolean> {
    await this.pending;
    return true;
  }

  override async close(): Promise<void> {
    await this.pending;
  }
}
