---
description: Review unanswered Instagram and Threads comments and approve drafted replies
argument-hint: [--since DAYS] [--platform instagram|threads]
---

# /replies

Run the reply review loop: scan for unanswered comments, triage, draft in the
user's voice, present for approval.

## Steps

1. Parse flags: `--since DAYS` (default 7), `--platform instagram|threads`
   (default: both). Pass through to `scan.py`.
2. Read `skills/reply/SKILL.md` and follow it exactly.
3. Make sure `scripts/voice.md` exists. If not, draft one from recent
   captions/replies and have the user correct it before drafting anything.
4. Run `python3 scripts/scan.py --config scripts/config.json` (create the
   config from `scripts/config.example.json` on first run).
5. For each queued comment, draft a reply per the voice rules. Group the
   review as **needs you** (questions, collab, sensitive) and **ready to
   send** (drafted). Show comment + post context + draft.
6. On explicit approval of a batch: run
   `python3 scripts/scan.py --handled <id> [<id> ...]` and hand over clean
   copy-paste blocks grouped by post, ready to paste into the apps.
7. Report the outcome: how many handled, how many still need the user, how
   many spam filtered. Never claim anything was posted — it wasn't; the
   user posts from the copy-paste blocks.
