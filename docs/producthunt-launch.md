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

## Video

`docs/assets/producthunt/blare-demo.mp4` — 25 seconds, 1280x720, silent, 550 KB.
Title, the code being typed, 500 errors firing, then the result: 1 delivered,
499 suppressed. Those numbers are from a real run against the published
package, not a mock-up.

`blare-demo.gif` (1.2 MB) is the same thing for places that will not take a
video: the README, Reddit, Twitter.

Product Hunt prefers a YouTube link over an upload. Upload the MP4 to YouTube
as unlisted and paste the link in the video field.

---

## Maker's first comment

Post this as the very first comment, within a minute of going live. It matters
more than the description — it is what people actually read.

---

Every production error at my old job went to Slack. Worked fine until a
connection pool died and the same exception fired a few hundred times in five
minutes. One Slack message each.

Someone muted the channel. That's worse than having no alerts, because now you
think you're covered.

I patched it with some throttling and a counter in Redis. Then I switched jobs
and wrote basically the same thing again. So I packaged it.

```
pip install blare
import blare; blare.init()
```

Point `BLARE_SINKS` at your webhook and your existing `logger.error` calls
start showing up in Slack, Discord or Teams. Same for crashes and framework
500s. No server, no dashboard, no dependencies.

Sending is the easy part. The work went into not sending. Identical errors get
grouped by type, by the line in your code (not the line inside the DB driver),
and by the message with the variable bits stripped out. So "User 4821 not
found" and "User 9173 not found" count as one problem. You get one alert per
problem per 5 minutes, with a count of everything it held back.

Python and Node are both out. I wrote the spec and the test fixtures before any
code, so both ports produce the same fingerprint for the same error. Built
Python first, then TypeScript expecting a week of debugging. Fixtures passed on
the first run.

It's v0.1.0. Well tested, but no real incident has hit it yet. No history or
search either, so if you need to look something up next week use Sentry or
Bugsink instead.

Go port next. Happy to answer anything, and curious how you deal with alert
fatigue.

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
