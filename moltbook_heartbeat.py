#!/usr/bin/env python3
"""
Moltbook Heartbeat: check status, DMs, feed. Optional skill-version check.
Uses MOLTBOOK_API_KEY. Output follows heartbeat response format for Bintly.
"""

import json
import os
import urllib.request
import urllib.error

BASE = "https://www.moltbook.com/api/v1"
SKILL_JSON = "https://www.moltbook.com/skill.json"


def _auth_header() -> dict:
    key = (os.environ.get("MOLTBOOK_API_KEY") or os.environ.get("BINTLY_API_KEY") or "").strip()
    if not key:
        return {}
    return {"Authorization": f"Bearer {key}"}


def _get(path: str, params: dict | None = None) -> dict | list:
    url = f"{BASE}/{path.lstrip('/')}"
    if params:
        q = "&".join(f"{k}={v}" for k, v in params.items())
        url = f"{url}?{q}" if "?" not in path else f"{url}&{q}"
    req = urllib.request.Request(url, headers=_auth_header(), method="GET")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except (urllib.error.HTTPError, urllib.error.URLError, json.JSONDecodeError, OSError) as e:
        return {"_error": str(e)}


def _get_skill_version() -> str | None:
    try:
        req = urllib.request.Request(SKILL_JSON)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("version")
    except Exception:
        return None


def run_heartbeat(
    check_skill: bool = True,
    check_status: bool = True,
    check_dm: bool = True,
    check_feed: bool = False,
) -> str:
    """
    Run one heartbeat cycle. Returns a single message in the heartbeat response format.
    """
    if not _auth_header():
        return "Hey! MOLTBOOK_API_KEY is not set. I can't check Moltbook until that's configured."

    parts = []
    need_human = []
    dm_activity = []

    if check_skill:
        ver = _get_skill_version()
        if ver:
            parts.append(f"Skill version: {ver}")

    if check_status:
        status_data = _get("agents/status")
        if isinstance(status_data, dict) and "_error" not in status_data:
            st = status_data.get("status", "")
            if st == "pending_claim":
                need_human.append("I'm still unclaimed. Please complete the claim flow so I can use Moltbook.")
            elif st == "claimed":
                pass  # ok
            else:
                parts.append(f"Agent status: {st}")

    if check_dm:
        dm = _get("agents/dm/check")
        if isinstance(dm, dict) and "_error" not in dm:
            pending = dm.get("pending_requests") or dm.get("pending_requests_count") or 0
            unread = dm.get("unread_messages") or dm.get("unread_count") or 0
            if isinstance(pending, list):
                pending = len(pending)
            if isinstance(unread, list):
                unread = len(unread)
            if pending and pending > 0:
                need_human.append(f"A molty wants to start a private conversation ({pending} pending). Should I accept?")
                dm_activity.append(f"{pending} new DM request(s)")
            if unread and unread > 0:
                dm_activity.append(f"{unread} unread DM(s)")

    if check_feed:
        feed = _get("feed", {"sort": "new", "limit": "5"})
        if isinstance(feed, list) and len(feed) > 0:
            parts.append(f"Feed: {len(feed)} recent items")
        elif isinstance(feed, dict) and "_error" not in feed:
            posts = feed.get("posts", feed.get("items", []))
            if posts:
                parts.append(f"Feed: {len(posts)} items")

    if need_human:
        return "Hey! " + " ".join(need_human)

    if dm_activity:
        return "Checked Moltbook - " + "; ".join(dm_activity) + "."

    if parts:
        return "Checked Moltbook - " + "; ".join(parts) + "."

    return "HEARTBEAT_OK - Checked Moltbook, all good!"


def main():
    import argparse
    p = argparse.ArgumentParser(description="Moltbook heartbeat: check status, DMs, optional feed.")
    p.add_argument("--no-skill", action="store_true", help="Skip skill version check.")
    p.add_argument("--no-status", action="store_true", help="Skip agent status check.")
    p.add_argument("--no-dm", action="store_true", help="Skip DM check.")
    p.add_argument("--feed", action="store_true", help="Check feed.")
    args = p.parse_args()
    msg = run_heartbeat(
        check_skill=not args.no_skill,
        check_status=not args.no_status,
        check_dm=not args.no_dm,
        check_feed=args.feed,
    )
    print(msg)


if __name__ == "__main__":
    main()
