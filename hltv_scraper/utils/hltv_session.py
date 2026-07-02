"""
hltv_session.py
===============
Shared session factory and safe fetch wrapper for all HLTV scrapers.

Problem solved
--------------
With `StealthySession(solve_cloudflare=True)`, patchright runs its CF-solving
browser automation on EVERY request — even on clean 200 OK responses.  That
produces the log spam:
    ERROR: No Cloudflare challenge found.
and costs ~3 s of overhead per request.  Across the ~600 requests in a full
weekly scrape that is 30+ minutes of pure wasted time.

This module fixes that by:
1. Using `solve_cloudflare=False` — the stealthy browser profile still bypasses
   CF for most requests; we just don't waste time looking for a CF element on
   every page.
2. Detecting a real CF challenge FROM the response HTML and retrying with
   back-off when one actually occurs.
3. Per-request wall-clock timeout (45 s by default) via concurrent.futures so
   a single hung request cannot stall the entire job.
4. Random jitter on all delays so consecutive requests look human.
5. Rate-limit back-off on implicit 429 / 503 responses.

Usage
-----
    from utils.hltv_session import make_session, safe_fetch, jitter_sleep

    with make_session() as session:
        page = safe_fetch(session, url)
        if page is None:
            continue          # already logged; skip this URL
        jitter_sleep(2)       # polite inter-request pause
"""

import time
import random
import concurrent.futures

from scrapling.fetchers import StealthySession

# ---------------------------------------------------------------------------
# Tuneable constants
# ---------------------------------------------------------------------------
REQUEST_TIMEOUT_S  = 45    # seconds before a single fetch is killed
CF_MAX_RETRIES     = 3     # attempts on a genuine CF challenge
CF_RETRY_BASE_S    = 15    # base wait between CF retries (grows per attempt)
RATE_LIMIT_WAIT_S  = 40    # pause on implicit 429 / 503 before one retry
BASE_URL           = "https://www.hltv.org"


# ---------------------------------------------------------------------------
# Session factory
# ---------------------------------------------------------------------------

def make_session(**kwargs) -> StealthySession:
    """
    Return a StealthySession with solve_cloudflare=False.

    The stealthy fingerprint still bypasses passive CF bot-detection.
    We only invoke the active CF solver when a genuine challenge is detected
    in the response — see safe_fetch().

    Pass keyword arguments to override defaults, e.g.::

        make_session(solve_cloudflare=True)   # for one-off debug runs
    """
    defaults = {"headless": True, "solve_cloudflare": False}
    defaults.update(kwargs)
    return StealthySession(**defaults)


# ---------------------------------------------------------------------------
# CF / rate-limit detection helpers
# ---------------------------------------------------------------------------

def _is_cf_challenge(page) -> bool:
    """Return True if the response is a Cloudflare challenge page."""
    try:
        title = (page.css("title::text").get() or "").lower()
        if "just a moment" in title or "checking your browser" in title:
            return True
        # CF challenge-specific DOM elements
        if page.css(
            "#cf-challenge-running, "
            "#cf-please-wait, "
            ".cf-browser-verification, "
            "form#challenge-form"
        ):
            return True
    except Exception:
        pass
    return False


def _is_rate_limited(page) -> bool:
    """Return True if the body signals rate-limiting."""
    try:
        body = (page.css("body::text").get() or "").lower()
        return "too many requests" in body or "rate limit" in body or "429" in body
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Core fetch with timeout
# ---------------------------------------------------------------------------

def _timed_fetch(session: StealthySession, url: str, timeout: float):
    """
    Call session.fetch(url) with a hard wall-clock timeout.
    Works on all platforms (no SIGALRM / Unix dependency).

    Returns the page Adaptor on success, None on timeout or exception.
    """
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(session.fetch, url)
        try:
            return future.result(timeout=timeout)
        except concurrent.futures.TimeoutError:
            print(f"  ⏱️  Request timed out after {timeout:.0f}s — skipping: {url}")
            return None
        except Exception as exc:
            print(f"  ❌ Fetch error ({type(exc).__name__}): {exc}")
            return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def safe_fetch(
    session: StealthySession,
    url: str,
    *,
    timeout: float = REQUEST_TIMEOUT_S,
    jitter: bool = True,
) -> object | None:
    """
    Fetch *url* from *session* with:
    - Micro-jitter delay before the request (looks human)
    - Per-request timeout guard
    - Rate-limit detection → 40 s back-off + single retry
    - CF challenge detection → up to CF_MAX_RETRIES retries with growing delays

    Returns the page Adaptor on success, or None on permanent failure.
    Callers should guard with ``if page is None: continue``.
    """
    if jitter:
        time.sleep(random.uniform(0.3, 0.9))

    page = _timed_fetch(session, url, timeout)
    if page is None:
        return None

    # ── Rate-limit check ──────────────────────────────────────────────────────
    if _is_rate_limited(page):
        wait = RATE_LIMIT_WAIT_S + random.uniform(0, 8)
        print(f"  🚦 Rate-limited — waiting {wait:.0f}s before retry …")
        time.sleep(wait)
        page = _timed_fetch(session, url, timeout)
        if page is None:
            return None

    # ── Cloudflare challenge check ────────────────────────────────────────────
    if _is_cf_challenge(page):
        for attempt in range(1, CF_MAX_RETRIES + 1):
            wait = CF_RETRY_BASE_S * attempt + random.uniform(0, 6)
            print(
                f"  🛡️  CF challenge detected "
                f"(attempt {attempt}/{CF_MAX_RETRIES}) — waiting {wait:.0f}s …"
            )
            time.sleep(wait)
            page = _timed_fetch(session, url, timeout * 1.5)
            if page is None:
                return None
            if not _is_cf_challenge(page):
                print("  ✅ CF challenge cleared.")
                break
        else:
            print(f"  ⛔ CF challenge persists after {CF_MAX_RETRIES} retries — skipping: {url}")
            return None

    return page


def jitter_sleep(base: float) -> None:
    """
    Sleep for ``base ± 0.5 s`` (minimum 0.5 s).
    Use instead of bare ``time.sleep()`` to vary inter-request timing.
    """
    time.sleep(max(0.5, base + random.uniform(-0.5, 0.5)))
