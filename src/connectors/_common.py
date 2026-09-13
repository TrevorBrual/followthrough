"""Shared connector plumbing: the dry-run switch and a retry wrapper."""

import os
import time

import requests
from dotenv import load_dotenv

load_dotenv()


def owner_label(item: dict) -> str:
    """Display name for an owner. The extractor returns None when nobody
    claimed the task; only the apps need a human-readable stand-in."""
    return item.get("owner") or "Unassigned"


def dry_run() -> bool:
    """Read DRY_RUN at call time so tests and the eval harness can flip it."""
    return os.getenv("DRY_RUN", "true").lower() in ("1", "true", "yes")


def request_with_retry(method: str, url: str, attempts: int = 3, **kwargs):
    """POST/PATCH with backoff. Retries timeouts, 429s, and 5xx; raises otherwise."""
    delay = 1.0
    for attempt in range(1, attempts + 1):
        try:
            response = requests.request(method, url, timeout=15, **kwargs)
            if response.status_code < 400:
                return response
            retryable = response.status_code == 429 or response.status_code >= 500
            if not retryable or attempt == attempts:
                response.raise_for_status()
        except requests.Timeout:
            if attempt == attempts:
                raise
        time.sleep(delay)
        delay *= 2
    raise RuntimeError(f"{method} {url} failed after {attempts} attempts")
