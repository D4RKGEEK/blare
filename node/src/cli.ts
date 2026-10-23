#!/usr/bin/env node
/**
 * `npx blare` — check a configuration without writing any code.
 *
 * Prints the resolved settings and offers to send one test alert, so "is this
 * wired up?" is answerable before an incident rather than during one.
 */

import { Blare } from "./client.js";
import { Config } from "./config.js";
import { ConfigError } from "./errors.js";
import { VERSION } from "./event.js";
import { detectProvider } from "./sinks/index.js";

export async function main(argv: string[] = process.argv.slice(2)): Promise<number> {
  if (argv.includes("--help") || argv.includes("-h")) {
    process.stdout.write(
      "Usage: npx blare [--send]\n\n" +
        "  --send     deliver one test alert to every configured sink\n" +
        "  --version  print the version\n",
    );
    return 0;
  }
  if (argv.includes("--version")) {
    process.stdout.write(`blare ${VERSION}\n`);
    return 0;
  }

  let config: Config;
  try {
    config = Config.fromEnv();
  } catch (error) {
    if (error instanceof ConfigError) {
      process.stderr.write(`configuration error: ${error.message}\n`);
      return 2;
    }
    throw error;
  }

  const out = (line: string) => process.stdout.write(`${line}\n`);
  out(`blare ${VERSION} (spec 1)`);
  out(`  service      ${config.service}`);
  out(`  environment  ${config.environment}`);
  out(`  level        ${config.level}`);
  out(`  dedupe       ${config.dedupeWindow}s window, ` +
    `max ${config.maxPerHour || "unlimited"}/hour`);
  out(`  state        ${config.state}`);
  out(`  resolve      ${config.resolveAfter || "off"}`);
  if (config.ignore.length) out(`  ignoring     ${config.ignore.join(", ")}`);

  if (config.sinks.length === 0) {
    out("\nNo sinks configured. Set BLARE_SINKS to your webhook URL.");
    return 1;
  }

  out("  sinks");
  for (const spec of config.sinks) {
    try {
      const [provider, url] = detectProvider(spec);
      // The webhook path is the credential, so only the host is ever printed.
      const host = url.includes("://") ? (new URL(url).host as string) : url;
      out(`    - ${provider.padEnd(8)} ${host}`);
    } catch (error) {
      out(`    ! ${(error as Error).message}`);
      return 2;
    }
  }

  if (!config.enabled) {
    out("\nBLARE_ENABLED is false, so nothing would be sent.");
    return 0;
  }
  if (!argv.includes("--send")) {
    out("\nRun with --send to deliver one test alert.");
    return 0;
  }

  const client = new Blare({ synchronous: true });
  out("\nsending test alert...");
  let failures = 0;
  for (const [target, ok] of await client.selftest()) {
    out(`  ${ok ? "ok  " : "FAIL"} ${target}`);
    if (!ok) failures += 1;
  }
  await client.close();
  return failures ? 1 : 0;
}

const invokedDirectly =
  typeof process.argv[1] === "string" && /[\\/]cli\.js$/.test(process.argv[1]);
if (invokedDirectly) {
  main().then((code) => process.exit(code), (error) => {
    process.stderr.write(`${String(error)}\n`);
    process.exit(1);
  });
}
