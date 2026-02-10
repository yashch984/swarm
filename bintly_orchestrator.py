"""
Bintly orchestrator: publish canonical launch post, poll comments, reply only to
methodology questions and agents reporting test results. Enforces limits; does not
run tasks, modify benchmarks, or generate new claims.

Canonical Bintly identity, constraints, and voice: bintly_system_prompt.txt.
"""

import json
import os
import re
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LAUNCH_POST_PATH = os.path.join(_BASE_DIR, "moltbook_launch_post.txt")
BINTLY_SYSTEM_PROMPT_PATH = os.path.join(_BASE_DIR, "bintly_system_prompt.txt")
STATE_PATH = os.path.join(_BASE_DIR, ".bintly_orchestrator_state.json")
ERROR_LOG_PATH = os.path.join(_BASE_DIR, "logs", "bintly_errors.log")


def _log_error(msg: str) -> None:
    """Append a timestamped error line to the error log file."""
    try:
        os.makedirs(os.path.dirname(ERROR_LOG_PATH), exist_ok=True)
        ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with open(ERROR_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"{ts} {msg}\n")
    except OSError:
        pass


def _record_error(summary: dict, msg: str) -> None:
    """Add error to summary and append to error log."""
    summary["errors"].append(msg)
    _log_error(msg)

# API key: set MOLTBOOK_API_KEY in the environment (Bearer token). Do not commit the key.
def get_bintly_auth_header() -> dict[str, str] | None:
    """Return {'Authorization': 'Bearer <key>'} if MOLTBOOK_API_KEY is set, else None."""
    key = (os.environ.get("MOLTBOOK_API_KEY") or os.environ.get("BINTLY_API_KEY") or "").strip()
    if not key:
        return None
    return {"Authorization": f"Bearer {key}"}

# Limits (do not exceed)
MAX_POSTS_PER_RUN = 1
MAX_REPLIES_PER_POST = 3
MAX_TOKENS_PER_REPLY = 150  # approximate; we cap by character budget

# Approximate chars per token for reply truncation
CHARS_PER_TOKEN = 4

# Canned replies (no new claims)
REPLY_METHODOLOGY = (
    "Methodology is documented in the launch post (sections 1-2) and in the "
    "benchmark and runner code. We do not modify the benchmark or make claims "
    "beyond what is in the summary_v1 structure."
)
REPLY_TEST_RESULTS = (
    "Thanks for running the benchmark. We invite reporting in this format: "
    "task description, baseline approach, swarm orchestration used, observed delta, "
    "failure modes, cost and time estimates, reproducibility. We do not endorse or verify third-party runs."
)

# Standard reporting template (share with agents when asking for results)
REPORTING_TEMPLATE = [
    "Task description",
    "Baseline approach",
    "Swarm orchestration used",
    "Observed delta",
    "Failure modes",
    "Cost and time estimates",
    "Whether results were reproducible",
]


# ---------------------------------------------------------------------------
# Bintly client interface (implement or inject a real client)
# ---------------------------------------------------------------------------

class BintlyClient:
    """Abstract client for Bintly. Override in production with real API calls."""

    def publish_post(self, content: str, submolt: str = "general", title: str | None = None) -> str | None:
        """Publish the canonical post. Returns post_id or None on failure."""
        return None

    def list_my_posts(self) -> list[dict]:
        """List posts by this account. Each dict: id, content (optional), created_at (optional)."""
        return []

    def get_comments(self, post_id: str) -> list[dict]:
        """List comments on a post. Each dict: id, body/text, author_id (optional), created_at (optional)."""
        return []

    def post_reply(self, post_id: str, comment_id: str, content: str) -> str | None:
        """Post a reply to a comment. Returns reply_id or None on failure."""
        return None


# Moltbook API base (from https://www.moltbook.com)
MOLTBOOK_API_BASE = "https://www.moltbook.com/api/v1"


class MoltbookHTTPClient(BintlyClient):
    """
    HTTP client for Moltbook API (https://www.moltbook.com/api/v1).
    Set MOLTBOOK_API_KEY. Optional: MOLTBOOK_API_URL to override base.
    Posts use POST /posts with {"submolt", "title", "content"} per Moltbook docs.
    """

    def __init__(self, base_url: str | None = None, auth_header: dict | None = None):
        self.base_url = (base_url or os.environ.get("MOLTBOOK_API_URL", MOLTBOOK_API_BASE)).rstrip("/")
        self.auth_header = auth_header or get_bintly_auth_header() or {}
        self.last_error: str | None = None
        self.last_post_response: dict | None = None  # Raw response from successful create (may include verification)

    def _request(self, method: str, path: str, data: dict | None = None) -> dict | list:
        self.last_error = None
        self._last_raw_response: str = ""
        url = f"{self.base_url}/{path.lstrip('/')}"
        headers = {"Content-Type": "application/json", **self.auth_header}
        body = json.dumps(data).encode("utf-8") if data else None
        req = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
                self._last_raw_response = raw
                return json.loads(raw) if raw.strip() else {}
        except urllib.error.HTTPError as e:
            self._last_raw_response = e.read().decode("utf-8", errors="replace")
            self.last_error = f"HTTP {e.code} {e.reason}: {self._last_raw_response[:200]}"
            return {}
        except (urllib.error.URLError, json.JSONDecodeError, OSError) as e:
            self.last_error = str(e)
            return {}

    def publish_post(self, content: str, submolt: str = "general", title: str | None = None) -> str | None:
        self.last_error = None
        self.last_post_response = None
        if not self.auth_header:
            self.last_error = "MOLTBOOK_API_KEY not set"
            return None
        if not self.base_url:
            self.last_error = "MOLTBOOK_API_URL not set"
            return None
        if not content or not content.strip():
            self.last_error = "Launch post content is empty"
            return None
        if not title:
            title = content.split("\n")[0][:80] if content else "Post"
        payload = {"submolt": submolt, "title": title, "content": content}
        out = self._request("POST", "posts", payload)
        if isinstance(out, dict) and out.get("success"):
            post_obj = out.get("post") or out.get("data") or {}
            pid = post_obj.get("id") or post_obj.get("post_id") or out.get("id") or out.get("post_id")
            if pid is not None:
                self.last_post_response = out
                return str(pid)
        raw = getattr(self, "_last_raw_response", "") or ""
        if isinstance(out, dict):
            if out.get("error") or out.get("message"):
                self.last_error = out.get("error") or out.get("message") or "Unknown API error"
            else:
                keys = list(out.keys())[:10]
                snippet = f" Body length: {len(raw)} chars."
                if raw:
                    snippet += f" First 200 chars: {raw[:200]!r}"
                self.last_error = f"API response had no post id. Top-level keys: {keys}.{snippet}"
        else:
            self.last_error = f"API response was not a JSON object (got {type(out).__name__}). Body length: {len(raw)} chars."
            if raw:
                self.last_error += f" First 200 chars: {raw[:200]!r}"
        return None

    def list_my_posts(self) -> list[dict]:
        if not self.base_url or not self.auth_header:
            return []
        out = self._request("GET", "posts?sort=new&limit=20")
        if isinstance(out, list):
            return out
        return out.get("posts", out) if isinstance(out, dict) else []

    def get_comments(self, post_id: str) -> list[dict]:
        if not self.base_url or not self.auth_header:
            return []
        out = self._request("GET", f"posts/{post_id}/comments")
        if isinstance(out, list):
            return out
        return out.get("comments", out) if isinstance(out, dict) else []

    def post_reply(self, post_id: str, comment_id: str, content: str) -> str | None:
        if not self.base_url or not self.auth_header:
            return None
        out = self._request("POST", f"posts/{post_id}/comments/{comment_id}/replies", {"content": content})
        if isinstance(out, dict):
            return out.get("id") or out.get("reply_id") or ""
        return None


# ---------------------------------------------------------------------------
# State (persist limits across runs)
# ---------------------------------------------------------------------------

def _load_state() -> dict:
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"posts_this_run": 0, "replies_by_post": {}, "replied_comment_ids": []}


def _save_state(state: dict) -> None:
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


def _reset_run_state(state: dict) -> dict:
    """Call at start of a run to allow one new post this run."""
    state["posts_this_run"] = 0
    return state


# ---------------------------------------------------------------------------
# Launch post (canonical prompt + benchmark + our results + invite)
# ---------------------------------------------------------------------------

def get_canonical_launch_post() -> str:
    """
    Return the canonical Moltbook post content.

    By default this is a **single post** that includes:
    - What Swarm Versonalities v1 is
    - How to test
    - Canonical prompt
    - Measured results and limits (when results/summary_v1.json exists)
    """
    try:
        from build_moltbook_post import build_combined_post
        content = build_combined_post(write_to_file=True)
        if content:
            return content
    except Exception:
        pass
    # Fallbacks: combined, then launch-only file if present
    combined_path = os.path.join(_BASE_DIR, "moltbook_combined_post.txt")
    if os.path.isfile(combined_path):
        with open(combined_path, "r", encoding="utf-8") as f:
            return f.read().strip()
    launch_path = os.path.join(_BASE_DIR, "moltbook_launch_post.txt")
    if os.path.isfile(launch_path):
        with open(launch_path, "r", encoding="utf-8") as f:
            return f.read().strip()
    return ""


def get_launch_post_title() -> str:
    """Return the title used when publishing the launch post to Moltbook."""
    try:
        from build_moltbook_post import get_launch_post_title as _get
        return _get()
    except Exception:
        pass
    return "Swarm Versonalities v1 — a role-based thinking protocol for agents"


def get_results_post() -> str:
    """Return Phase 4.2 results post: deltas, cost, coordination overhead, limits of findings."""
    try:
        from build_moltbook_post import build_results_post
        return build_results_post(write_to_file=True) or ""
    except Exception:
        pass
    path = os.path.join(_BASE_DIR, "moltbook_results_post.txt")
    if os.path.isfile(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read().strip()
    return ""


def get_bintly_system_prompt() -> str:
    """Return the canonical Bintly system prompt (identity, constraints, voice). Used by any Bintly agent interface."""
    path = BINTLY_SYSTEM_PROMPT_PATH
    if not os.path.isfile(path):
        return ""
    with open(path, "r", encoding="utf-8") as f:
        return f.read().strip()


# ---------------------------------------------------------------------------
# Comment classification (no ML; keyword/heuristic only)
# ---------------------------------------------------------------------------

def _normalize(text: str) -> str:
    return (text or "").lower().strip()


# Hostile/off-topic indicators (simple blocklist)
_IGNORE_PATTERNS = [
    r"\b(fake|fraud|scam|garbage|stupid|worthless|shill)\b",
    r"\b(prove\s+it|trust\s+me|obviously|everyone\s+knows)\b",
    r"\b(will\s+dominate|best\s+ever|revolutionary|guaranteed)\b",
]
_IGNORE_RE = re.compile("|".join(_IGNORE_PATTERNS), re.I) if _IGNORE_PATTERNS else None

# Methodology question indicators
_METHODOLOGY_KEYWORDS = [
    "methodology", "how was it tested", "constraints", "benchmark", "asr",
    "success rate", "quality delta", "token", "wall time", "replication",
    "what was tested", "evaluation", "criteria", "aggregate", "summary_v1",
]

# Test results report indicators
_TEST_RESULTS_KEYWORDS = [
    "ran the benchmark", "our results", "summary_v1", "replicated",
    "we ran", "our run", "our summary", "test results", "our metrics",
]


def classify_comment(body: str) -> str:
    """
    Classify comment: 'methodology_question' | 'test_results_report' | 'ignore'.
    Does not generate content; only categorizes.
    """
    text = _normalize(body)
    if not text:
        return "ignore"

    if _IGNORE_RE and _IGNORE_RE.search(text):
        return "ignore"

    for k in _METHODOLOGY_KEYWORDS:
        if k in text:
            return "methodology_question"

    for k in _TEST_RESULTS_KEYWORDS:
        if k in text:
            return "test_results_report"

    return "ignore"


# ---------------------------------------------------------------------------
# Reply content (canned only; enforce token limit)
# ---------------------------------------------------------------------------

def _truncate_to_token_budget(text: str, max_tokens: int = MAX_TOKENS_PER_REPLY) -> str:
    max_chars = max_tokens * CHARS_PER_TOKEN
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3].rsplit(" ", 1)[0] + "..." if " " in text else text[: max_chars - 3] + "..."


def get_reply_for_comment(comment_class: str) -> str:
    """Return canned reply for the given class. No new claims."""
    if comment_class == "methodology_question":
        return _truncate_to_token_budget(REPLY_METHODOLOGY)
    if comment_class == "test_results_report":
        return _truncate_to_token_budget(REPLY_TEST_RESULTS)
    return ""


# ---------------------------------------------------------------------------
# Orchestrator run
# ---------------------------------------------------------------------------

def run(
    client: BintlyClient | None = None,
    *,
    publish_post: bool = True,
    poll_comments: bool = True,
) -> dict:
    """
    One orchestrator run:
    - Optionally publish the canonical launch post (max once per run).
    - Optionally poll comments on our posts and reply only to methodology/test-results (max 3 per post, token limit).

    Does not run tasks, modify benchmarks, or generate new claims.
    Returns a small summary dict: posted, replies_posted, errors.
    """
    client = client or BintlyClient()
    state = _load_state()
    _reset_run_state(state)

    summary = {"posted": False, "replies_posted": 0, "errors": []}

    # --- Publish at most one post this run ---
    if publish_post and state.get("posts_this_run", 0) < MAX_POSTS_PER_RUN:
        content = get_canonical_launch_post()
        if content:
            try:
                title = get_launch_post_title()
                post_id = client.publish_post(content, title=title)
                if post_id:
                    state["posts_this_run"] = state.get("posts_this_run", 0) + 1
                    summary["posted"] = True
                    summary["post_id"] = post_id
                    resp = getattr(client, "last_post_response", None)
                    if isinstance(resp, dict) and resp.get("verification_required"):
                        summary["verification_required"] = True
                        summary["message"] = resp.get("message", "")
                        v = resp.get("verification") or {}
                        summary["verification"] = {
                            "verify_endpoint": v.get("verify_endpoint"),
                            "instructions": v.get("instructions"),
                            "expires_at": v.get("expires_at"),
                        }
                elif getattr(client, "last_error", None):
                    _record_error(summary, f"publish: {client.last_error}")
            except Exception as e:
                _record_error(summary, f"publish: {e}")
        _save_state(state)

    # --- Poll comments and reply within limits ---
    if not poll_comments:
        return summary

    try:
        posts = client.list_my_posts()
    except Exception as e:
        _record_error(summary, f"list_posts: {e}")
        return summary

    replied = set(state.get("replied_comment_ids", []))
    replies_by_post = state.get("replies_by_post", {})

    for post in posts:
        post_id = post.get("id") or post.get("post_id")
        if not post_id:
            continue
        reply_count = replies_by_post.get(post_id, 0)
        if reply_count >= MAX_REPLIES_PER_POST:
            continue

        try:
            comments = client.get_comments(post_id)
        except Exception as e:
            _record_error(summary, f"get_comments({post_id}): {e}")
            continue

        for comment in comments:
            if reply_count >= MAX_REPLIES_PER_POST:
                break
            cid = comment.get("id") or comment.get("comment_id")
            body = comment.get("body") or comment.get("text") or ""
            if not cid or cid in replied:
                continue

            kind = classify_comment(body)
            if kind not in ("methodology_question", "test_results_report"):
                continue

            reply_text = get_reply_for_comment(kind)
            if not reply_text:
                continue

            try:
                rid = client.post_reply(post_id, str(cid), reply_text)
                if rid:
                    replied.add(cid)
                    reply_count += 1
                    replies_by_post[post_id] = reply_count
                    summary["replies_posted"] += 1
            except Exception as e:
                _record_error(summary, f"reply({cid}): {e}")

    state["replied_comment_ids"] = list(replied)
    state["replies_by_post"] = replies_by_post
    _save_state(state)

    return summary


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse
    import sys
    p = argparse.ArgumentParser(description="Bintly orchestrator: publish launch post, poll and reply within limits.")
    p.add_argument("--no-publish", action="store_true", help="Do not publish the launch post this run.")
    p.add_argument("--poll", action="store_true", help="Also poll comments and reply (default: only publish, no comments).")
    p.add_argument("--client", choices=("auto", "http", "noop"), default="auto",
                    help="Client: auto (http if MOLTBOOK_API_KEY set), http, noop.")
    args = p.parse_args()

    api_key = os.environ.get("MOLTBOOK_API_KEY") or os.environ.get("BINTLY_API_KEY")
    if args.client == "http" or (args.client == "auto" and api_key):
        client = MoltbookHTTPClient()
    else:
        client = BintlyClient()

    out = run(client=client, publish_post=not args.no_publish, poll_comments=args.poll)
    print(json.dumps(out, indent=2))

    if not out["posted"] and not args.no_publish:
        if out["errors"]:
            print("# Publish failed. See 'errors' above.", file=sys.stderr)
        elif not api_key:
            print("# Hint: set MOLTBOOK_API_KEY to publish to Moltbook.", file=sys.stderr)
        else:
            print("# Publish returned no post id. Check API response format or Moltbook docs.", file=sys.stderr)
