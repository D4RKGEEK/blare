/** Sink registry. SPEC.md section 3. */

import { ConfigError } from "../errors.js";
import { Sink, detectProvider } from "./base.js";
import { ConsoleSink } from "./console.js";
import { DiscordSink } from "./discord.js";
import { GenericSink } from "./generic.js";
import { SlackSink } from "./slack.js";
import { TeamsSink } from "./teams.js";

const BY_PROVIDER: Record<string, new (url: string, timeout?: number) => Sink> = {
  slack: SlackSink,
  discord: DiscordSink,
  teams: TeamsSink,
  generic: GenericSink,
  console: ConsoleSink,
};

/** Create the sink for one `BLARE_SINKS` entry. */
export function buildSink(spec: string, timeout = 5): Sink {
  const [provider, url] = detectProvider(spec);
  const Constructor = BY_PROVIDER[provider];
  if (!Constructor) throw new ConfigError(`unknown provider ${JSON.stringify(provider)}`);
  return new Constructor(url, timeout);
}

export function buildSinks(specs: readonly string[], timeout = 5): Sink[] {
  return specs.map((spec) => buildSink(spec, timeout));
}

export { ConsoleSink, DiscordSink, GenericSink, Sink, SlackSink, TeamsSink, detectProvider };
export * from "./base.js";
