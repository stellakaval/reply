---
name: reply
description: Engagement copilot for Instagram and Threads. Finds unanswered comments on recent posts, triages them (question, compliment, collab inquiry, spam, sensitive), and drafts replies in the user's voice for one-tap approval. Use when someone wants help keeping up with comments or DMs-adjacent engagement without sounding like a bot.
---

# reply

Engagement is half the algorithm and the most tedious part of posting. `reply`
does the grind: it scans your recent Instagram and Threads posts for comments
you haven't answered, sorts them into what needs you vs. what can be drafted,
and writes replies in your voice. You approve; nothing ever posts itself.

Backed by `scripts/scan.py`, which drives the `instagram-cli` and `threads-cli`
CLIs. Drafting is the agent's job — the script only gathers and triages.

## The core loop

1. **Scan.** Run `python3 scripts/scan.py --config scripts/config.json`.
   It resolves your accounts, pulls recent posts (default: last 7 days, up to
   10 posts per platform), fetches their comments in batches, and writes a
   review queue to `logs/queue_YYYY-MM-DD.json` (plus a JSONL run log).
   Comments you've already handled (recorded in `state/seen.json`) are
   skipped. Obvious spam is filtered, not drafted.
2. **Triage.** Every queued comment carries a `category`:
   - `question` — needs a real answer; draft one, flag if you're unsure.
   - `compliment` / `conversational` — safe to draft.
   - `collab` — brand/deal/partnership inquiry; draft a warm holding reply
     and surface it prominently. Money lives here.
   - `sensitive` — negativity, hate, controversy. Never draft a clapback.
     Flag for the user, suggest hide/delete/block only as options.
   - `spam` — filtered from the queue entirely; reported as a count.
3. **Draft.** Write each reply in the voice from `scripts/voice.md`
   (see "Voice" below). Keep it short — one or two sentences, matching the
   energy of the comment. No hashtags in replies, no corporate sign-offs,
   no emoji spam unless that's genuinely how the user writes.
4. **Review.** Present the queue grouped as **needs you** (questions you're
   unsure about, collab, sensitive) and **ready to send** (drafted). Show the
   comment, the post it was on, and your draft side by side.
5. **Approve.** Only on explicit approval, mark comments handled
   (`python3 scripts/scan.py --handled <comment-id> ...`) and hand over
   clean copy-paste blocks. Posting itself is manual in v1 — see
   "Honest limitations."

## Voice

`scripts/voice.md` is the user's editable voice profile: tone notes plus a few
real examples of how they actually reply. If it doesn't exist, build a first
draft from their recent captions (`instagram-cli posts`) and their past replies,
then ask them to correct it. The profile is theirs to edit — never overwrite
their edits, only append new observations with their permission.

Drafting rules:
- Sound like a person, not a brand. Contractions, fragments, and lowercase
  are fine if that's their style.
- Mirror the commenter's energy: hype gets hype back, a sincere question
  gets a sincere answer.
- Never invent facts (prices, dates, links). If a question needs a fact you
  don't have, draft "let me check and get back to you" style, or flag it.
- One reply per comment. Don't stack multiple thoughts.

## Scheduling

Engagement compounds with consistency. The recommended setup is twice daily
(morning + evening) via cron or equivalent:

```
0 9,19 * * * /usr/bin/python3 /path/to/reply/scripts/scan.py --config /path/to/reply/scripts/config.json
```

The scan itself only reads; drafting happens when the user runs `/replies`
and reviews the queue. For a fully hands-off digest, pair with a notifier
that sends the queue summary (counts by category) so the user only opens the
queue when there's something worth answering.

## Safety

- **Never auto-post.** There is no approved path from draft to published
  without the user saying so, out loud, for that specific batch.
- **Never engage with hate.** Flag, suggest hide/delete/block, move on.
- **Never reply to obvious spam** (crypto promos, "DM to collab" bots,
  link drops). Filter and report the count.
- **Don't feed trolls.** Heated threads get flagged as `sensitive`, not
  drafted.
- **Rate limits are respected.** Batched reads, small post windows, no
  polling loops. If a CLI returns 429, back off and report it.
- **Privacy.** Comment text is the commenter's; don't paste it into
  unrelated contexts. The queue files live in `logs/` (gitignored).

## Honest limitations

- **Drafts only in v1.** Neither the Instagram nor the Threads CLI can post
  comments, so approved replies are handed over as copy-paste blocks for now.
  A provider interface exists for a future auto-post path (e.g. Instagram
  Graph API comment replies on a professional account) — it is not wired up,
  and the plugin says so instead of pretending.
- **Threads is read-only** via its CLI: comments can be read and triaged,
  drafts are copy-paste.
- **"Already replied" detection is heuristic.** If you answered from the
  native app, the scanner can't always tell; marking handled on approval
  keeps the queue clean going forward.
- **DMs are out of scope.** Comment engagement only — inbox belongs to the
  messaging skills, not this plugin.
