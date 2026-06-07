"""Opt-in on-disk response cache for vnstock string results.

For a research tool, reproducibility matters: two runs of the same ticker and
date should be able to see the same fundamentals and news. vnstock fetches those
live every call, so this module freezes them to disk when
``vnstock_cache_enabled`` is True.

Design:
  * Default OFF — live runs stay fresh (news is time-sensitive). When disabled,
    ``cached_call`` is a transparent pass-through with zero behavior change.
  * Scope — string-returning methods (fundamentals + news). OHLCV is already
    cached in ``load_ohlcv`` and is not duplicated here.
  * Key — sha1(method + normalized args). Files live under
    ``data_cache_dir/responses/``.
  * Never cache errors or empty results, so a transient miss can't poison the
    cache (mirrors the load_ohlcv empty-cache guard).
"""

from __future__ import annotations

import hashlib
import logging
import os
from typing import Callable

from .config import get_config

logger = logging.getLogger(__name__)


def _is_cacheable(result: str) -> bool:
    """True when a producer result is real data worth caching.

    Empty strings, "No ..." sentinels (e.g. "No news found"), and early "Error"
    messages are skipped so a transient miss is never frozen to disk.
    """
    if not result:
        return False
    head = result[:24]
    if result.startswith("No ") or "Error" in head or "NO_DATA_AVAILABLE" in head:
        return False
    return True


def cached_call(method: str, key_parts: list, producer: Callable[[], str]) -> str:
    """Return ``producer()``, served from disk when caching is enabled.

    When ``vnstock_cache_enabled`` is False this calls ``producer`` directly and
    returns its result unchanged. When True, a cache hit returns the stored
    string and ``producer`` is not called; a miss calls ``producer`` and stores
    a real (non-empty, non-error) result.
    """
    config = get_config()
    if not config.get("vnstock_cache_enabled", False):
        return producer()

    raw_key = "|".join([method, *(str(p) for p in key_parts)])
    digest = hashlib.sha1(raw_key.encode("utf-8")).hexdigest()
    cache_dir = os.path.join(config["data_cache_dir"], "responses")
    os.makedirs(cache_dir, exist_ok=True)
    path = os.path.join(cache_dir, f"{method}-{digest}.txt")

    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                return f.read()
        except OSError as e:
            logger.warning("vn_cache: read failed for %s, refetching: %s", path, e)

    result = producer()

    if _is_cacheable(result):
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(result)
        except OSError as e:
            logger.warning("vn_cache: write failed for %s: %s", path, e)
    return result
