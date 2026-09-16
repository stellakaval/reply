# reply

An engagement copilot for Instagram and Threads, packaged as a Muse plugin.

It scans your recent posts for comments you haven't answered, triages them
(question, compliment, collab inquiry, spam, sensitive), and drafts replies in
your voice for one-tap approval. **Drafts only — it never auto-posts.**

## Why

Engagement is half the algorithm and the most tedious part of posting. ChatGPT
apps can help you *write* content, but they can't watch your comments on a
schedule, remember your voice, or learn what you already handled. A plugin
running inside your agent can.

## How it works

1. `scripts/scan.py` pulls your recent posts (default: last 7 days) via the
   `instagram-cli` and `threads-cli` CLIs, fetches their comments in batches,
   and writes a review queue to `logs/queue_YYYY-MM-DD.json`.
2. Comments are triaged: `question`, `conversational`, `collab` (brand/deal
   inquiries surface prominently), `sensitive` (flagged, never drafted),
   `spam` (filtered, counted). The scan also reports `top_fans` (your most
   frequent commenters — prioritize them, relationship signals compound) and
   a `pin_candidate` per post (best comment to pin in the first hour).
3. The agent drafts replies using your editable voice profile
   (`scripts/voice.md`, with a monthly trend radar) and presents them grouped
   as **needs you** vs. **ready to send** — newest first, since the first
   30–60 minutes after posting is the highest-leverage reply window.
4. You approve a batch; approved comments are marked handled
   (`state/seen.json`) so the queue stays clean.

## Install

**Claude Code:**

```
/plugin marketplace add stellakaval/reply
/plugin install reply@reply
```

**Muse (native plugin system, in your terminal):**

```
muse plugins marketplace add stellakaval stellakaval/reply
muse plugins install reply@stellakaval
muse plugins approve reply
```

Then run `/replies` to review your queue.

## Quickstart

```bash
# 1. Copy the example config and voice profile, make them yours
cp scripts/config.example.json scripts/config.json
cp scripts/voice.example.md scripts/voice.md
# edit: your IG/Threads usernames (so your own comments are skipped),
# then fix up the voice examples until they sound like you

# 2. Make sure your accounts are connected
instagram-cli accounts   # if empty, run instagram-cli connect-url
threads-cli accounts     # if empty, run threads-cli connect-url

# 3. Run a scan (reads only — nothing posts, nothing sends)
python3 scripts/scan.py --config scripts/config.json

# 4. Twice-daily scans keep the queue fresh (drafting still needs you)
crontab -e
# 0 9,19 * * * /usr/bin/python3 /path/to/reply/scripts/scan.py --config /path/to/reply/scripts/config.json

# 5. Mark comments handled after approving their replies
python3 scripts/scan.py --handled <comment-id> [<comment-id> ...]
```

## Honest limitations

- **Drafts only.** Neither the Instagram nor the Threads CLI can post
  comments, so approved replies are handed over as copy-paste blocks. A
  provider slot exists for a future auto-post path (e.g. Instagram Graph API
  comment replies on a professional account) — it is not wired up.
- **Threads is read-only** via its CLI: comments are read and triaged, drafts
  are copy-paste.
- **"Already replied" is heuristic.** Replies sent from the native apps aren't
  always detectable; marking handled on approval keeps the queue clean.
- **Comments only.** DMs are out of scope.
- **Rate limits respected, not dodged.** Batched reads, small windows, no
  polling loops.
