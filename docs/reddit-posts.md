# Reddit posts — blare

Four ready-to-paste posts. **Stagger them over 1–2 weeks**, not the same day:
posting the same link across subreddits within hours is the pattern Reddit's
spam filter catches, and a shadow-removed post gets you nothing.

Check each subreddit's current sidebar before posting — rules change, and a
removed post can cost you the ability to post there again.

---

## 1. r/Python — the big one

r/Python enforces a format for project posts (flair: **Showcase**). The three
headings below are required; posts without them get removed. Verify the current
wording in the sidebar first.

**Title**

```
blare — error alerting that sends one Slack message instead of 847
```

**Body**

```markdown
**What My Project Does**

Two lines (`import blare; blare.init()`) turn your existing `logger.error`
calls, unhandled exceptions and framework 500s into Slack, Discord or Teams
messages. No server, no dashboard, zero runtime dependencies.

The actual work is in *not* sending. Identical failures are fingerprinted
together — from the error type, the line in your code (not the line inside the
DB driver), and the message with its variable parts stripped — so
`User 4821 not found` and `User 9173 not found` are one problem. You get one
alert per problem per 5 minutes, carrying the count of everything it suppressed.

Integrations: `logging`, FastAPI, Starlette, Litestar, Quart, Flask, Django,
Celery, any WSGI app.

**Target Audience**

Teams who already pipe errors to Slack and have watched that channel get muted
during an incident. It's a library, not a service — meant for production, but
it's v0.1.0 and hasn't been through a real incident yet, so I'd say "try it on
a side project or staging first" rather than claiming battle-tested.

**Comparison**

- **Apprise / Shoutrrr** deliver messages to 100+ services but capture nothing
  — you write the glue and the throttling yourself.
- **Sentry / GlitchTip / Bugsink** capture properly but you run a server, a
  database and a dashboard. blare is not a replacement: no history, no search,
  no UI. Plenty of teams would run both.
- **`slack-logger`-style packages** are one framework, one channel, no grouping.

blare is the middle: capture + grouping + delivery, as a library.

---

`pip install blare`

- Repo: https://github.com/D4RKGEEK/blare
- Demo (press the button to flood it): https://d4rkgeek.github.io/blare/
- PyPI: https://pypi.org/project/blare/

Apache-2.0. Go port is next.
```

---

## 2. r/node

**Title**

```
Built an error alerter for Node that groups identical failures into one Slack message
```

**Body**

```markdown
A connection pool ran dry at my last job and the same exception fired a few
hundred times in five minutes — each one its own Slack message. Someone muted
the channel, which is worse than having no alerts at all.

So: `npm install @geekvb/blare`, then

```js
import blare from "@geekvb/blare";
blare.init();
```

and `BLARE_SINKS=<your webhook URL>`.

Unhandled exceptions and rejected promises are captured automatically. pino and
winston take a stream/transport; Express, Fastify, NestJS and Next.js take one
line. Slack, Discord and Teams are detected from the webhook hostname.

The grouping is the point — identical failures collapse to one message with a
count, there's a hard ceiling of 20 alerts/hour, and secrets (bearer tokens,
JWTs, AWS keys, URL passwords) are stripped before anything leaves.

Ships ESM + CJS with types, zero runtime dependencies, Node 18.17+.

- Repo: https://github.com/D4RKGEEK/blare
- Demo: https://d4rkgeek.github.io/blare/
- npm: https://www.npmjs.com/package/@geekvb/blare

v0.1.0 and honest about it — well tested, not yet through a real incident.
Would like to hear how others handle alert fatigue.
```

---

## 3. r/devops — lead with alert fatigue, not the tool

This crowd is allergic to tool promos. The post has to be about the problem.

**Title**

```
The muted Slack channel problem, and what I did about it
```

**Body**

```markdown
Every team I've worked on eventually does this: wire production errors to a
Slack webhook, love it for a month, then a cascade fires the same exception 800
times and someone mutes the channel. After that you have alerting that looks
fine on the architecture diagram and warns nobody.

The fix is always the same three things, and always written from scratch:

1. **Fingerprint** the failure so identical ones group — from the error type,
   the line in *your* code (not the frame inside the DB driver where it
   surfaced), and the message with its variable parts normalised away.
2. **One alert per problem per window**, carrying the count of what it
   suppressed, so nothing is lost and you don't need a second summary message.
3. **A hard ceiling** per hour, which *reports how many it dropped* — a rate
   limit that hides its own existence is a lie by omission.

I got tired of rewriting it and made it a library. Python and Node, no server,
no dashboard, zero dependencies. Deduplication state is a lock-guarded file
shared across workers on a host, or Redis across hosts.

https://github.com/D4RKGEEK/blare

Genuinely curious how others handle this — do you throttle at the app, at the
webhook, or just accept the noise and route to PagerDuty instead?
```

---

## 4. r/opensource or r/SideProject — the spec-first angle

**Title**

```
I wrote the spec before any code, then built two implementations. The fixtures passed first run.
```

**Body**

```markdown
I wanted an error-alerting library in several languages. The obvious route is
write one, then port it — which produces drift: implementations that *claim*
the same behaviour and quietly diverge.

So I wrote a SPEC.md first, defining fingerprinting, the dedupe window, frame
selection, message normalisation and redaction exactly, with no code anywhere.
Then a folder of language-neutral JSON fixtures that every port's test suite
reads **directly** — not transcribed per language, read from the same bytes.

Built Python first. Then TypeScript, expecting a week of debugging tiny
mismatches.

The fingerprint fixtures passed on the first run. Same sixteen hex characters
in both languages, so a Node service and a Python service in one fleet group
the same failure into the same alert.

Adding Go now means implementing the spec and running the fixtures — there's
nothing to guess about what "correct" means.

- Repo: https://github.com/D4RKGEEK/blare
- The spec: https://github.com/D4RKGEEK/blare/blob/main/SPEC.md
- Fixtures: https://github.com/D4RKGEEK/blare/tree/main/conformance

Apache-2.0. Recommend it if you're planning a multi-language library — the
up-front cost was maybe a day and it paid for itself on the second port.
```

---

## Subreddits worth it, and ones to skip

| Subreddit | Verdict |
| --- | --- |
| **r/Python** | Best single post. Required format above. |
| **r/node** | Good, relaxed about show-and-tell. |
| **r/devops** | Works only if framed as the problem, not the tool. |
| **r/opensource**, **r/SideProject** | Easy, lower traffic. |
| r/FastAPI, r/django, r/flask, r/expressjs | Small but highly relevant. Tailor the integration line. |
| r/javascript | Self-promo restricted to **Showoff Saturday**. Check first. |
| r/programming | Will likely be removed as self-promo. Only works as a link to the dev.to writeup, not the repo. |
| r/selfhosted | Skip. blare runs no server, so it isn't what that sub means by self-hosted. |
| r/ExperiencedDevs | Skip. No self-promotion, enforced. |

## Rules that actually get posts removed

- **Never ask for stars or upvotes.** Instant removal in most of these.
- **Comment before you post.** A brand-new account dropping a GitHub link is
  filtered automatically in r/Python and r/devops.
- **Reply to every comment**, especially critical ones. The top comment on a
  tool post is often "why not just use X" — answering that well is what
  converts readers.
- **Keep "v0.1.0, not yet through a real incident" in every post.** Reddit will
  find it anyway, and saying it first is the difference between credible and
  caught.
