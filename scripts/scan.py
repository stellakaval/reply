#!/usr/bin/env python3
"""reply scan: gather unanswered Instagram/Threads comments into a review queue.

Reads only. Drafting happens in the agent (see skills/reply/SKILL.md).
Writes the queue to logs/queue_YYYY-MM-DD.json and appends a run record to
logs/scans.jsonl. Handled comment ids live in state/seen.json (--handled
marks them).
"""

import argparse
import json
import os
import re
import subprocess
import sys
from collections import Counter
from datetime import date, datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
STATE_DIR = os.path.join(ROOT, "state")
LOGS_DIR = os.path.join(ROOT, "logs")
SEEN_FILE = os.path.join(STATE_DIR, "seen.json")


def sh(args, timeout=60):
    try:
        p = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    except (subprocess.SubprocessError, FileNotFoundError) as e:
        return None, str(e)
    if p.returncode != 0:
        return None, (p.stderr or p.stdout or "unknown error").strip()[:300]
    try:
        return json.loads(p.stdout), None
    except json.JSONDecodeError:
        return None, "non-JSON output: " + p.stdout[:200]


def load_seen():
    try:
        with open(SEEN_FILE) as f:
            data = json.load(f)
            return set(data if isinstance(data, list) else [])
    except (OSError, json.JSONDecodeError):
        return set()


def save_seen(seen):
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(SEEN_FILE, "w") as f:
        json.dump(sorted(seen), f, indent=2)


def load_config(path):
    with open(path) as f:
        return json.load(f)


# ---- comment shape normalization (CLI schemas are defensive targets) ----

def _pick(d, *keys):
    for k in keys:
        if isinstance(d, dict) and d.get(k) not in (None, ""):
            return d[k]
    return None


def norm_comment(platform, raw, post_ref):
    cid = str(_pick(raw, "comment_id", "id", "pk") or "")
    text = str(_pick(raw, "comment_text", "text", "body") or "").strip()
    author = _pick(raw, "author_name", "username", "user", "author") or {}
    if isinstance(author, dict):
        author = author.get("username") or author.get("text") or "unknown"
    author = str(author)
    ts = _pick(raw, "created_at", "timestamp", "taken_at")
    try:
        likes = int(_pick(raw, "like_count", "likes") or 0)
    except (TypeError, ValueError):
        likes = 0
    return {
        "platform": platform,
        "comment_id": cid,
        "post_ref": post_ref,
        "author": author,
        "author_id": str(_pick(raw, "author_id", "author_fbid") or ""),
        "text": text,
        "like_count": likes,
        "created_at": str(ts) if ts else None,
    }


def extract_comments(payload):
    """Find a list of comment dicts inside a CLI response of unknown shape."""
    if isinstance(payload, list):
        items = payload
    elif isinstance(payload, dict):
        # Instagram nests comments per post under post_groups
        if isinstance(payload.get("post_groups"), list):
            items = []
            for g in payload["post_groups"]:
                if isinstance(g, dict) and isinstance(g.get("comments"), list):
                    items.extend(g["comments"])
            return [i for i in items if isinstance(i, dict)]
        for key in ("comments", "items", "results", "data", "replies"):
            if isinstance(payload.get(key), list):
                items = payload[key]
                break
        else:
            return []
    else:
        return []
    return [i for i in items if isinstance(i, dict)]


def extract_posts(payload):
    if isinstance(payload, dict):
        posts = payload.get("posts")
        if isinstance(posts, list):
            return posts
    return extract_comments(payload)


# ---- triage ----

QUESTION_RE = re.compile(r"\?")
COLLAB_RE = re.compile(
    r"\b(collab|collaboration|partnership|brand deal|sponsor|paid promo|"
    r"ambassador|pr package|gifted|rate card|media kit)\b", re.I)
SENSITIVE_RE = re.compile(
    r"\b(hate|stupid|ugly|dumb|scam|fake|liar|shut up|kill yourself|kys)\b", re.I)
SPAM_RE = re.compile(
    r"(https?://\S+|t\.me/|whatsapp|dm (me|for)|crypto|forex|double your|"
    r"free followers|boost your (account|followers))", re.I)


def triage(text):
    t = text or ""
    if SPAM_RE.search(t):
        return "spam"
    if SENSITIVE_RE.search(t):
        return "sensitive"
    if COLLAB_RE.search(t):
        return "collab"
    if QUESTION_RE.search(t):
        return "question"
    return "conversational"


# ---- platform scans ----

def ig_account_id():
    data, err = sh(["instagram-cli", "accounts"])
    if err or not data:
        return None, err or "no accounts"
    accts = data if isinstance(data, list) else data.get("accounts", [])
    if not accts:
        return None, "no linked instagram account"
    a = accts[0]
    return (a.get("user_fbid") or a.get("id")), None


def scan_instagram(cfg, since_days, limit_posts, seen, own_names):
    aid, err = ig_account_id()
    if err:
        return [], {"platform": "instagram", "error": err}
    since = (datetime.now(timezone.utc) - timedelta(days=since_days)).strftime("%Y-%m-%d")
    posts, err = sh(["instagram-cli", "posts", "--account-id", str(aid),
                     "--limit", str(limit_posts), "--since", since])
    if err:
        return [], {"platform": "instagram", "error": err}
    post_list = extract_posts(posts)
    post_ids = [str(_pick(p, "post_id", "id", "pk") or "") for p in post_list]
    post_ids = [pid for pid in post_ids if pid]
    if not post_ids:
        return [], {"platform": "instagram", "posts_checked": 0}
    comments, err = sh(["instagram-cli", "fetch-post-comments",
                        "--account-id", str(aid),
                        "--post-ids", ",".join(post_ids),
                        "--since", since, "--limit", "50"])
    if err:
        return [], {"platform": "instagram", "error": err}
    queue, spam = [], 0
    for raw in extract_comments(comments):
        c = norm_comment("instagram", raw, str(_pick(raw, "post_id", "media_id") or ""))
        if not c["comment_id"] or not c["text"]:
            continue
        if c["author_id"] == str(aid) or c["author"].lower() in own_names:
            continue  # your own comment
        if c["comment_id"] in seen:
            continue
        cat = triage(c["text"])
        if cat == "spam":
            spam += 1
            continue
        c["category"] = cat
        queue.append(c)
    # Engagement intel: frequent commenters get priority (relationship signals
    # compound — the algorithm shows your posts more to people you interact with)
    top_fans = Counter(c["author"] for c in queue).most_common(5)
    # Pin candidate per post: most-liked substantive comment sets the thread tone
    pin_candidates = []
    by_post = {}
    for c in queue:
        by_post.setdefault(c["post_ref"], []).append(c)
    for post_ref, comments in by_post.items():
        best = max(comments, key=lambda c: (c["like_count"], len(c["text"])))
        if best["like_count"] > 0 or len(best["text"]) > 40:
            pin_candidates.append({
                "post_ref": post_ref,
                "comment_id": best["comment_id"],
                "author": best["author"],
                "text": best["text"][:120],
                "like_count": best["like_count"],
            })
    return queue, {"platform": "instagram", "posts_checked": len(post_ids),
                   "queued": len(queue), "spam_filtered": spam,
                   "top_fans": [{"author": a, "comments": n} for a, n in top_fans],
                   "pin_candidates": pin_candidates}


def th_account_id():
    data, err = sh(["threads-cli", "accounts"])
    if err or not data:
        return None, err or "no accounts"
    accts = data if isinstance(data, list) else data.get("accounts", [])
    if not accts:
        return None, "no linked threads account"
    return (accts[0].get("id") or accts[0].get("account_id")), None


def scan_threads(cfg, since_days, limit_posts, seen, own_names):
    aid, err = th_account_id()
    if err:
        return [], {"platform": "threads", "error": err}
    # Activity feed replies surface what needs answering; fall back to
    # profile threads if the feed shape is unusable.
    feed, ferr = sh(["threads-cli", "activity-feed", "--account-id", str(aid),
                     "--category-filter", "text_post_app_replies", "--first", "30"])
    queue, spam = [], 0
    items = extract_comments(feed) if not ferr else []
    for raw in items:
        c = norm_comment("threads", raw, str(_pick(raw, "post_id", "thread_id") or ""))
        if not c["comment_id"] or not c["text"]:
            continue
        if c["author"].lower() in own_names or c["comment_id"] in seen:
            continue
        cat = triage(c["text"])
        if cat == "spam":
            spam += 1
            continue
        c["category"] = cat
        queue.append(c)
    top_fans = Counter(c["author"] for c in queue).most_common(5)
    report = {"platform": "threads", "queued": len(queue),
              "spam_filtered": spam,
              "top_fans": [{"author": a, "comments": n} for a, n in top_fans]}
    if ferr:
        report["warning"] = ferr
        return queue, report
    return queue, report


def main():
    ap = argparse.ArgumentParser(description="Scan IG/Threads for unanswered comments.")
    ap.add_argument("--config", default=os.path.join(HERE, "config.example.json"))
    ap.add_argument("--since", type=int, default=None, help="days back to scan")
    ap.add_argument("--limit-posts", type=int, default=None)
    ap.add_argument("--platforms", default=None, help="comma list: instagram,threads")
    ap.add_argument("--handled", nargs="*", default=[],
                    help="comment ids to mark as handled")
    args = ap.parse_args()

    if args.handled:
        seen = load_seen()
        seen.update(args.handled)
        save_seen(seen)
        print(json.dumps({"marked_handled": len(args.handled),
                          "total_seen": len(seen)}))
        return 0

    cfg = load_config(args.config)
    since_days = args.since or cfg.get("since_days", 7)
    limit_posts = args.limit_posts or cfg.get("limit_posts", 10)
    platforms = (args.platforms or cfg.get("platforms", "instagram,threads")).split(",")
    platforms = [p.strip() for p in platforms if p.strip()]
    own_names = {n.lower() for n in cfg.get("own_usernames", []) if n}

    seen = load_seen()
    queue, reports = [], []
    if "instagram" in platforms:
        q, rep = scan_instagram(cfg, since_days, limit_posts, seen, own_names)
        queue += q
        reports.append(rep)
    if "threads" in platforms:
        q, rep = scan_threads(cfg, since_days, limit_posts, seen, own_names)
        queue += q
        reports.append(rep)

    os.makedirs(LOGS_DIR, exist_ok=True)
    today = date.today().isoformat()
    qpath = os.path.join(LOGS_DIR, f"queue_{today}.json")
    with open(qpath, "w") as f:
        json.dump({"generated_at": datetime.now(timezone.utc).isoformat(),
                   "reports": reports, "queue": queue}, f, indent=2)
    with open(os.path.join(LOGS_DIR, "scans.jsonl"), "a") as f:
        f.write(json.dumps({"at": datetime.now(timezone.utc).isoformat(),
                            "reports": reports,
                            "queued": len(queue)}) + "\n")

    by_cat = {}
    for c in queue:
        by_cat[c["category"]] = by_cat.get(c["category"], 0) + 1
    print(json.dumps({"queue_file": qpath, "total": len(queue),
                      "by_category": by_cat, "reports": reports}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
