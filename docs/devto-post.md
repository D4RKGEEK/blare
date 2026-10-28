---
title: The hard part of error alerting isn't sending. It's not sending.
published: false
description: I kept rewriting the same Slack webhook glue at work. So I built the library I wanted — and specified its behaviour before writing any code, which turned out to be the decision that mattered.
tags: opensource, node, python, webdev
cover_image: https://raw.githubusercontent.com/D4RKGEEK/blare/main/docs/assets/social-card.png
---

At work, every production failure showed up in Slack. I'd wired our logging so
that anything at `ERROR` level fired a webhook, and for a while it was great.
You push a bad deploy, you see it immediately, you fix it.

Then one evening a database connection pool ran dry, and the same exception
fired a few hundred times in five minutes. Each one its own Slack message.

You know what happens next. Someone mutes the channel. And a muted alerting
channel is strictly worse than no alerting channel, because now you think
you're covered.

I fixed it the way everyone fixes it: a bit of throttling, a counter, some
state in Redis. Then I changed jobs and wrote roughly the same code again.

So I made it a library.

## First I checked whether I needed to

I almost skipped this step, and I'm glad I didn't. The landscape splits
cleanly in two:

| | What it does | What's missing |
| --- | --- | --- |
| **Apprise**, **Shoutrrr** | Deliver one message to 100+ services | They don't *capture* anything. You write the glue. |
| **Sentry**, **GlitchTip**, **Bugsink** | Capture errors properly | You run a server, a database and a dashboard |
| `express-error-slack` and friends | The glue — for one framework, one channel | One language, no grouping, mostly unmaintained |

Apprise is excellent at what it does. So is Sentry. But if all you want is
"tell my team in Slack when production breaks," Apprise means writing the
capture layer yourself, and Sentry means running infrastructure to get a
dashboard you'll look at twice a year.

Nobody had built the middle: **capture plus grouping plus delivery, as a
library, with no server.** That's the gap I went for.

## The part everyone skips

Capturing errors is easy. Posting to a webhook is easy. I could write both
before lunch.

Deciding *which* of 847 identical failures deserves a message is the actual
product, and it's the part the weekend version always leaves out. That's why
the channel gets muted.

So the rule is: **one message per problem, not per crash.**

> 🟠 **OperationalError: connection pool exhausted**
> `checkout-api · production` — **847 times in the last 5 min**
> `app/payments.py:142 in charge`

One message. The other 846 occurrences aren't lost — they ride along as that
count. Which also means no background timer and no second "summary" message:
the summary *is* the next alert.

## Grouping is a hashing problem

"The same problem" needs a precise definition, so every failure reduces to a
fingerprint:

```
fingerprint = sha256(kind + type + location + normalized_message)[:16]
```

Two pieces do the real work.

**Normalizing the message.** Strip the parts that change between occurrences,
in a fixed order — quoted strings, emails, URLs, UUIDs, hex IDs, paths, IPs,
then numbers:

```
"User 4821 not found in '/srv/app/users.db' (attempt 3)"
                        ↓
"user <n> not found in <s> (attempt <n>)"
```

So `User 4821 not found` and `User 9173 not found` are one problem, not two.

**Picking the right line.** Walk the stack from the innermost frame outward
and take the first one that *isn't* in `site-packages`, `node_modules` or
`vendor`. You want the line in *your* code that caused the failure, not the
line inside the database driver where it happened to surface. One bug reached
by two code paths is still one bug.

On top of that: a hard ceiling of 20 alerts an hour, and the number dropped by
that ceiling reported on the next alert that gets through. A rate limit that
hides its own existence is a lie by omission.

## The decision that actually mattered

I wanted this in several languages. The obvious approach is to write one, then
port it, then port it again.

That produces drift. Three libraries that *claim* the same behaviour, group
things slightly differently, and whose docs quietly become fiction.

So I wrote the spec first — a `SPEC.md` defining fingerprinting, the dedupe
window, frame selection, normalization and redaction exactly, with no code
anywhere. Then a folder of language-neutral JSON fixtures:

```json
{
  "id": "varying-number-groups-together-a",
  "message": "User 4821 not found",
  "fingerprint": "b0a5839f239ce91c"
},
{
  "id": "varying-number-groups-together-b",
  "message": "User 9173 not found",
  "fingerprint": "b0a5839f239ce91c"
}
```

Every port's test suite reads those files **directly** — not transcribed into
each language, read from the same bytes. If a fixture changes, every port that
has drifted breaks.

I built Python first. Then TypeScript, expecting a week of debugging tiny
mismatches.

The fingerprint fixtures passed on the first run.

That's the payoff. A Node service and a Python service in the same fleet
produce the *identical* fingerprint for the identical failure. Not "similar
behaviour" — the same 16 hex characters. Adding Go now means implementing the
spec and running the fixtures; there's nothing to guess about what correct
means.

I don't think I'd have got that by porting.

## Using it

Python:

```bash
pip install blare
```

```python
import blare
blare.init()
```

Node:

```bash
npm install @geekvb/blare
```

```js
import blare from "@geekvb/blare";
blare.init();
```

Then one environment variable:

```bash
BLARE_SINKS=https://hooks.slack.com/services/T000/B000/xxxx
```

Paste whatever URL your chat tool gave you — Slack, Discord or Teams are
detected from the hostname. Nobody should have to learn a URL scheme to send a
message to a chat room.

From there, the `logger.error(...)` calls you already have become alerts. No
new code at the call sites. Frameworks take one line:

```python
app.add_middleware(BlareASGIMiddleware)       # FastAPI
```

```js
app.use(blareErrorHandler());                  // Express
```

Check it's wired up before you need it, rather than during the outage it was
installed for:

```bash
python -m blare --send
```

## Some decisions I'd defend

**No runtime dependencies**, either language. An alerting library should not be
able to break your deploy with a version conflict.

**Delivery never raises into the host**, never blocks the thread that raised
the error, and sits behind a bounded queue. If your chat provider goes down,
you lose alerts — you don't lose requests. Back-pressure from Slack must never
become back-pressure on production traffic.

**Crash capture re-raises.** Swallowing a crash in order to report it would be
a worse bug than the one being reported.

**Request bodies, local variables and query strings are never collected.** This
data goes to a third-party chat service. What does leave is scanned for bearer
tokens, JWTs, AWS keys, GitHub and Slack tokens, private keys, passwords inside
connection strings, and card numbers. Redaction runs *after* fingerprinting, so
changing a redaction rule can never regroup your history.

**It works across workers.** Dedupe state is a lock-guarded file shared by
every process on the host, so four Gunicorn workers seeing one crash send one
message rather than four.

## What it deliberately doesn't do

- **No history, no search, no dashboard.** It tells you something broke, then
  forgets. If you need to look a failure up next week, run an error tracker and
  let this stay out of it. Being the thin thing is the point.
- **No browser support.** A webhook URL in frontend JavaScript is a public
  secret — anyone can read it and flood your channel. Browser capture needs a
  relay through your own backend, which is a different product.
- **No Redis state in the Node port yet.** It falls back to the shared file and
  says so, rather than pretending to deduplicate across hosts.

## Honest status

This is **v0.1.0**. It has a few hundred tests, and the behaviour is pinned to
shared fixtures rather than to my memory of what I intended. But tested and
battle-proven are different claims, and I'm not going to pretend otherwise: it
hasn't yet run through a real production incident.

Go is next. If you want to write a port, the spec and the fixtures mean you
never have to ask me what the correct behaviour is — the JSON already says.

- **Repo:** https://github.com/D4RKGEEK/blare
- **Docs:** https://d4rkgeek.github.io/blare/
- **The spec:** https://github.com/D4RKGEEK/blare/blob/main/SPEC.md

Apache-2.0. If you've solved the muted-channel problem a different way, I'd
genuinely like to hear it.
