import hashlib
import logging
import math
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

def normalize_domain(domain: str) -> str:
    """
    Basic domain normalization: strip scheme, path, and lowercase.
    """
    if not domain:
        return ""
    d = domain.strip().lower()
    if "://" in d:
        d = d.split("://", 1)[1]
    d = d.split("/", 1)[0]
    d = d.split("?", 1)[0]
    return d

def utc_now_iso() -> str:
    """
    ISO-8601 timestamp with timezone, suitable for snapshotDate.
    """
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

def _hash_to_int(text: str) -> int:
    h = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return int(h[:12], 16)

def _pseudo_random_float(seed: int, minimum: float, maximum: float) -> float:
    """
    Deterministic pseudo-random float based on an integer seed.
    """
    # Simple LCG-based pseudo random
    a = 1664525
    c = 1013904223
    m = 2**32
    value = (a * seed + c) % m
    frac = value / m
    return minimum + (maximum - minimum) * frac

def _build_estimated_visits(base: int) -> Dict[str, int]:
    """
    Generate a 3-month descending visit history ending with base.
    """
    today = datetime.now(timezone.utc)
    months = []
    for i in range(2, -1, -1):
        month_date = (today.replace(day=1) - timedelta(days=30 * i)).replace(day=1)
        key = month_date.strftime("%Y-%m-01")
        months.append(key)

    # Simple decay factor
    visits = {}
    current = base
    for key in months[::-1]:
        visits[key] = max(1000, int(current))