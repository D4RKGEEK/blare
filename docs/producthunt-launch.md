# Product Hunt launch kit — blare

Everything needed to fill in the submission form. Character counts are verified
against Product Hunt's limits.

---

## Name

```
blare
```

## Tagline (limit 60 — yours currently says "Python" only)

**Use this one:**

```
Open-source error alerting for Python and Node.js
```
*49 characters.* Your draft says "for Python" and leaves Node out, which halves
the audience on a launch where Node developers are the larger group.

Alternatives:

| Tagline | Chars |
| --- | --- |
| `Production errors in Slack, Discord and Teams. Two lines.` | 57 |
| `Error alerts in Slack or Discord. Two lines, no server.` | 55 |
| `Send production errors to Slack in two lines of code` | 52 |

## Description (limit 260)

```
Error alerting in two lines. No server, no dashboard, and one message per problem instead of 847. Captures your existing logs, crashes and framework 500s, strips secrets, and posts to Slack, Discord or Teams. Python and Node.js, Apache-2.0.
```
*240 characters.* Your current draft is good but stops at the first sentence —
this keeps that opening and adds what it captures and which languages.

## Topics (pick 3)

1. **Developer Tools**
2. **Open Source**
3. **Productivity** — or **Bots** if offered

## Links

| Field | Value |
| --- | --- |
| Website | `https://d4rkgeek.github.io/blare/` |
| GitHub | `https://github.com/D4RKGEEK/blare` |
| PyPI | `https://pypi.org/project/blare/` |
| npm | `https://www.npmjs.com/package/@geekvb/blare` |

## Pricing

Choose **Free**. It is Apache-2.0 with no paid tier. Do not leave this blank —
an unanswered pricing field reads as "about to be monetised".

---

## Gallery images

In `docs/assets/producthunt/`, all 1270×760 (Product Hunt's recommended size).
Upload in this order — the first is the feed thumbnail.

| # | File | What it shows |
| --- | --- | --- |
| 1 | `1-hero.png` | Name, claim, the two lines, the grouped alert |
| 2 | `2-problem.png` | 847 messages without blare, one message with it |
| 3 | `3-integrations.png` | Frameworks and destinations |
| 4 | `4-spec.png` | Same failure, same fingerprint, across two languages |

Image 2 is the one that sells it. If Product Hunt only shows two, make sure
that one is second.

---

## Maker's first comment

Post this as the very first comment, within a minute of going live. It matters
more than the description — it is what people actually read.

---

At work, every production failure went to Slack. I had wired our logging so
anything at ERROR level fired a webhook, and for a while it was great.

Then a database connection pool ran dry and the same exception fired a few
hundred times in five minutes. Each one its own Slack message.

Someone muted the channel. A muted alerting channel is worse than no channel,
because now you think you're covered.

I fixed it the way everyone does — some throttling, a counter, state in Redis.
Then I changed jobs and wrote roughly the same code again. So I made it a
library.

**What it is:** two lines, and your existing `logger.error` calls plus
unhandled crashes become Slack, Discord or Teams messages. No server, no
dashboard, no account, zero runtime dependencies.

```
pip install blare        →  import blare; blare.init()
npm install @geekvb/blare →  import blare from "@geekvb/blare"; blare.init()
```

**The part that took the real work** isn't sending — it's *not* sending.
Identical failures are fingerprinted together from the error type, the line in
*your* code (not the line inside the database driver), and the message with its
variable parts stripped, so `User 4821 not found` and `User 9173 not found` are
one problem. You get one alert per problem per five minutes, carrying the count
of everything it suppressed.

**One decision I'd do again:** I wrote the behaviour spec before any code — how
fingerprinting works, the dedupe window, redaction — plus a folder of
language-neutral JSON fixtures every port's tests read directly. Then I built
Python, then TypeScript expecting a week of debugging mismatches. The
fingerprint fixtures passed first run. Same sixteen characters in both
languages.

**What it deliberately doesn't do:** no history, no search, no dashboard. If
you need to investigate a failure next week, run Sentry or Bugsink — different
problem, and they work fine alongside it. No browser support either: a webhook
URL in frontend JavaScript is a public secret anyone can use to flood your
channel.

**Honest status:** v0.1.0, a few hundred tests, and it has not yet been through
a real production incident. Tested and battle-proven are different claims.

Go is next. Happy to answer anything, and genuinely interested in how you've
solved the muted-channel problem differently.

---

## Launch timing

- **Go live at 12:01 AM PT.** Product Hunt's day resets then; posting later
  costs you hours of ranking time.
- **Tuesday, Wednesday or Thursday.** Monday is crowded, weekends are dead.
- Be available for the first 4 hours. Replying to every comment matters more
  than the vote count.

## Launch-day checklist

- [ ] Tagline mentions both Python and Node.js
- [ ] All four gallery images uploaded, `2-problem.png` second
- [ ] All four links added, pricing set to Free
- [ ] Maker comment posted within a minute of going live
- [ ] GitHub social preview set (Settings → General → Social preview →
      `docs/assets/social-card.png`) so shared links render properly
- [ ] dev.to post published the same morning, linking to the PH page
- [ ] Reply to every comment the same day

## Do not

- Ask for upvotes anywhere. Product Hunt detects vote rings and penalises them,
  and "please upvote" in a Slack group is exactly what they look for. Share the
  link and say you launched; that's allowed and effective.
- Claim it's a Sentry alternative. It will attract people who want history and
  search, who will bounce and say so in the comments.
- Hide the v0.1.0 status. Someone will check the repo within ten minutes.
  Saying it first makes you credible; being caught makes you not.
